"""Memory context service for injecting user context into prompts."""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models import MemoryFile, UserProfile

logger = logging.getLogger(__name__)

# Default memory files to create for new users
DEFAULT_MEMORY_FILES = {
    "USER.md": """# USER.md - About You

This file contains information about you that helps the AI assist you better.

## Personal Info
- Name: [Your name]
- Role: [Your role/profession]
- Location: [Your timezone/location]

## Preferences
- Communication style: [concise/detailed/casual/formal]
- Technical level: [beginner/intermediate/expert]
- Interests: [Your main interests]

## Projects
- [List your current projects]

## Notes
- [Any additional context you want the AI to know]
""",
    "CONTEXT.md": """# CONTEXT.md - Current Context

This file tracks what you're currently working on. Update it periodically.

## Current Focus
- [What are you working on right now?]

## Recent Decisions
- [Any recent decisions you've made]

## Active Questions
- [Questions you're currently exploring]

## Notes
- [Temporary notes, update regularly]
""",
    "PREFERENCES.md": """# PREFERENCES.md - Learned Preferences

This file tracks preferences learned from your interactions.
The AI updates this based on your feedback and choices.

## Coding Style
- Language preference: [Python/JavaScript/etc.]
- Framework preference: [React/Vue/etc.]
- Code style: [concise/verbose/etc.]

## Communication
- Response length: [brief/moderate/detailed]
- Explanation depth: [surface/moderate/deep]
- Technical jargon: [minimal/moderate/technical]

## Notes
- [Learned preferences will be added here]
"""
}


class MemoryContext:
    """Manage user memory files and inject context into prompts."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def get_or_create_user(self) -> UserProfile:
        """Get or create the default user profile."""
        result = await self.db.execute(select(UserProfile).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            user = UserProfile(
                name="User",
                preferences={}
            )
            self.db.add(user)
            await self.db.commit()
            await self.db.refresh(user)
            
            # Create default memory files
            await self._create_default_files(user.id)
        
        return user
    
    async def _create_default_files(self, user_id: str) -> None:
        """Create default memory files for a new user."""
        for name, content in DEFAULT_MEMORY_FILES.items():
            memory_file = MemoryFile(
                user_id=user_id,
                name=name,
                content=content,
                description=f"Default {name} file"
            )
            self.db.add(memory_file)
        
        await self.db.commit()
    
    async def get_memory_files(self) -> dict[str, str]:
        """Get all memory files for the current user."""
        user = await self.get_or_create_user()
        
        result = await self.db.execute(
            select(MemoryFile).where(MemoryFile.user_id == user.id)
        )
        files = result.scalars().all()
        
        return {f.name: f.content for f in files}
    
    async def build_context_prompt(self) -> str:
        """Build a context prompt from all memory files."""
        files = await self.get_memory_files()
        
        if not files:
            return ""
        
        context_parts = []
        
        # Add each memory file as a section
        for name, content in files.items():
            # Remove the .md extension for display
            section_name = name.replace(".md", "")
            context_parts.append(f"\n## {section_name}\n{content}")
        
        return "\n".join(context_parts)
    
    async def inject_context(self, system_prompt: str, persona_name: str = None) -> str:
        """Inject memory context into a system prompt."""
        context = await self.build_context_prompt()
        
        if not context:
            return system_prompt
        
        # Build the injected context
        injected = f"""<user_context>
This context is provided to help you assist the user better. Use it to personalize your responses.

{context}
</user_context>"""
        
        # Inject before the main instructions
        if "\n\n" in system_prompt:
            # If there's a paragraph break, inject after first paragraph
            parts = system_prompt.split("\n\n", 1)
            return f"{parts[0]}\n\n{injected}\n\n{parts[1]}"
        else:
            # Otherwise prepend
            return f"{injected}\n\n{system_prompt}"
    
    async def update_memory_file(self, name: str, content: str) -> None:
        """Update a memory file."""
        user = await self.get_or_create_user()
        
        result = await self.db.execute(
            select(MemoryFile).where(
                MemoryFile.user_id == user.id,
                MemoryFile.name == name
            )
        )
        memory_file = result.scalar_one_or_none()
        
        if memory_file:
            memory_file.content = content
        else:
            memory_file = MemoryFile(
                user_id=user.id,
                name=name,
                content=content
            )
            self.db.add(memory_file)
        
        await self.db.commit()
    
    async def learn_preference(self, key: str, value: str, source: str = "chat", context: str = None) -> None:
        """Record a learned preference from chat interaction."""
        from app.models import PreferenceTracking
        
        user = await self.get_or_create_user()
        
        preference = PreferenceTracking(
            user_id=user.id,
            key=key,
            value=value,
            source=source,
            confidence="medium",
            context=context
        )
        self.db.add(preference)
        await self.db.commit()
        
        logger.info(f"Learned preference: {key}={value} (source: {source})")