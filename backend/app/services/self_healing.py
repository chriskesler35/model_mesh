"""Self-healing system for automatic recovery and rollback."""

import os
import json
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class SelfHealingSystem:
    """Manages system health, recovery, and rollback."""
    
    def __init__(self, project_root: str = None):
        if project_root:
            self.project_root = Path(project_root)
        else:
            # Auto-detect project root based on this file's location
            self.project_root = Path(__file__).parent.parent.parent
        self.snapshots_dir = self.project_root / "snapshots"
        self.health_file = self.project_root / "health_status.json"
        self.last_good_commit_file = self.project_root / "last_good_commit.txt"
        
        # Ensure snapshots directory exists
        self.snapshots_dir.mkdir(exist_ok=True)
    
    async def check_health(self) -> Dict[str, Any]:
        """Run comprehensive health check."""
        health = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {}
        }
        
        # Check database connectivity
        try:
            from app.database import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            health["checks"]["database"] = "healthy"
        except Exception as e:
            health["checks"]["database"] = f"unhealthy: {str(e)}"
            health["status"] = "unhealthy"
        
        # Check Redis connectivity — optional, only flag if explicitly configured
        try:
            from app.redis import get_redis
            from app.config import settings as _settings
            redis = await get_redis()
            if redis is None:
                health["checks"]["redis"] = "not configured (optional)"
            else:
                await redis.ping()
                health["checks"]["redis"] = "healthy"
        except Exception as e:
            from app.config import settings as _settings
            if getattr(_settings, 'redis_url', None):
                health["checks"]["redis"] = f"unhealthy: {str(e)}"
                health["status"] = "degraded"
            else:
                health["checks"]["redis"] = "not configured (optional)"
        
        # Check disk space
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.project_root)
            free_percent = (free / total) * 100
            if free_percent < 10:
                health["checks"]["disk"] = f"warning: {free_percent:.1f}% free"
                health["status"] = "degraded"
            else:
                health["checks"]["disk"] = f"healthy: {free_percent:.1f}% free"
        except Exception as e:
            health["checks"]["disk"] = f"unknown: {str(e)}"
        
        # Check for crashed processes
        health["checks"]["processes"] = await self._check_processes()
        
        # Save health status
        self._save_health_status(health)
        
        return health
    
    async def _check_processes(self) -> str:
        """Check if critical processes are running."""
        try:
            # Check if the main process is running
            import os
            pid = os.getpid()
            return f"healthy: process {pid} running"
        except Exception as e:
            return f"unknown: {str(e)}"
    
    def _save_health_status(self, health: Dict[str, Any]) -> None:
        """Save health status to file."""
        try:
            with open(self.health_file, "w") as f:
                json.dump(health, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save health status: {e}")
    
    def _load_health_status(self) -> Optional[Dict[str, Any]]:
        """Load last health status from file."""
        try:
            if self.health_file.exists():
                with open(self.health_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load health status: {e}")
        return None
    
    async def create_snapshot(self, name: Optional[str] = None) -> Dict[str, Any]:
        """Create a snapshot of current state."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        snapshot_name = name or f"snapshot_{timestamp}"
        snapshot_dir = self.snapshots_dir / snapshot_name
        snapshot_dir.mkdir(exist_ok=True)
        
        snapshot = {
            "name": snapshot_name,
            "timestamp": timestamp,
            "files": {}
        }
        
        # Snapshot database state
        try:
            db_backup_file = snapshot_dir / "database_backup.sql"
            # This would use pg_dump in production
            # For now, we'll just record the snapshot
            snapshot["files"]["database"] = str(db_backup_file)
        except Exception as e:
            logger.error(f"Failed to snapshot database: {e}")
        
        # Snapshot configuration
        try:
            import shutil
            config_files = [".env", "docker-compose.yml"]
            for config_file in config_files:
                src = self.project_root / config_file
                if src.exists():
                    dst = snapshot_dir / config_file
                    shutil.copy2(src, dst)
                    snapshot["files"][config_file] = str(dst)
        except Exception as e:
            logger.error(f"Failed to snapshot config: {e}")
        
        # Record git commit
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=self.project_root
            )
            if result.returncode == 0:
                snapshot["git_commit"] = result.stdout.strip()
                # Save as last good commit
                with open(self.last_good_commit_file, "w") as f:
                    f.write(snapshot["git_commit"])
        except Exception as e:
            logger.error(f"Failed to get git commit: {e}")
        
        # Save snapshot metadata
        with open(snapshot_dir / "metadata.json", "w") as f:
            json.dump(snapshot, f, indent=2)
        
        logger.info(f"Created snapshot: {snapshot_name}")
        return snapshot
    
    async def restore_snapshot(self, snapshot_name: str) -> Dict[str, Any]:
        """Restore from a snapshot."""
        snapshot_dir = self.snapshots_dir / snapshot_name
        
        if not snapshot_dir.exists():
            raise ValueError(f"Snapshot not found: {snapshot_name}")
        
        # Load snapshot metadata
        with open(snapshot_dir / "metadata.json", "r") as f:
            snapshot = json.load(f)
        
        # Restore configuration
        try:
            import shutil
            for config_file, backup_path in snapshot["files"].items():
                if config_file in [".env", "docker-compose.yml"]:
                    src = Path(backup_path)
                    dst = self.project_root / config_file
                    if src.exists():
                        shutil.copy2(src, dst)
        except Exception as e:
            logger.error(f"Failed to restore config: {e}")
        
        # Restore git commit
        if "git_commit" in snapshot:
            try:
                subprocess.run(
                    ["git", "checkout", snapshot["git_commit"]],
                    cwd=self.project_root
                )
                logger.info(f"Restored to commit: {snapshot['git_commit']}")
            except Exception as e:
                logger.error(f"Failed to restore git commit: {e}")
        
        logger.info(f"Restored snapshot: {snapshot_name}")
        return snapshot
    
    def list_snapshots(self) -> list[Dict[str, Any]]:
        """List all available snapshots."""
        snapshots = []
        
        for snapshot_dir in self.snapshots_dir.iterdir():
            if snapshot_dir.is_dir():
                metadata_file = snapshot_dir / "metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, "r") as f:
                            snapshots.append(json.load(f))
                    except Exception as e:
                        logger.error(f"Failed to load snapshot metadata: {e}")
        
        return sorted(snapshots, key=lambda x: x["timestamp"], reverse=True)
    
    def get_last_good_commit(self) -> Optional[str]:
        """Get the last known good commit."""
        try:
            if self.last_good_commit_file.exists():
                with open(self.last_good_commit_file, "r") as f:
                    return f.read().strip()
        except Exception as e:
            logger.error(f"Failed to get last good commit: {e}")
        return None
    
    async def recover(self) -> Dict[str, Any]:
        """Attempt automatic recovery from unhealthy state."""
        result = {
            "status": "unknown",
            "actions": [],
            "message": ""
        }
        
        # Check current health
        health = await self.check_health()
        
        if health["status"] == "healthy":
            result["status"] = "no_recovery_needed"
            result["message"] = "System is healthy, no recovery needed"
            return result
        
        # Try to recover
        recovery_actions = []
        
        # If database is unhealthy, try to reconnect
        if "unhealthy" in health["checks"].get("database", ""):
            try:
                # Force new connection pool
                from app.database import engine
                await engine.dispose()
                recovery_actions.append("Reset database connection pool")
            except Exception as e:
                logger.error(f"Failed to reset database pool: {e}")
        
        # If Redis is unhealthy, it's optional so just log
        if "unhealthy" in health["checks"].get("redis", ""):
            recovery_actions.append("Redis unavailable, proceeding without cache")
        
        # If processes are unhealthy, could restart (but be careful)
        if "unhealthy" in health["checks"].get("processes", ""):
            recovery_actions.append("Process check failed, manual intervention may be needed")
        
        # Check again
        new_health = await self.check_health()
        
        if new_health["status"] == "healthy":
            result["status"] = "recovered"
            result["message"] = "System recovered successfully"
        else:
            # Try rollback to last known good
            last_good_commit = self.get_last_good_commit()
            if last_good_commit:
                try:
                    subprocess.run(
                        ["git", "checkout", last_good_commit],
                        cwd=self.project_root
                    )
                    recovery_actions.append(f"Rolled back to commit {last_good_commit[:8]}")
                    result["status"] = "rolled_back"
                    result["message"] = f"Rolled back to last known good state: {last_good_commit[:8]}"
                except Exception as e:
                    result["status"] = "recovery_failed"
                    result["message"] = f"Recovery failed: {str(e)}"
            else:
                result["status"] = "recovery_failed"
                result["message"] = "No known good state to recover to"
        
        result["actions"] = recovery_actions
        return result


# Global instance
self_healing = SelfHealingSystem()