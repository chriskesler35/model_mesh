"""
Model management utilities - cleanup and resync operations.

Usage:
  python -m app.scripts.manage_models cleanup
  python -m app.scripts.manage_models status
  python -m app.scripts.manage_models sync
"""

import asyncio
import sys
import logging
from typing import Optional
from sqlalchemy import select, delete
from app.database import AsyncSessionLocal
from app.models.model import Model
from app.models.provider import Provider
from app.routes.model_sync import run_model_sync, discover_provider_models

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def show_status():
    """Show current model inventory by provider."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Model, Provider)
            .join(Provider, Model.provider_id == Provider.id)
            .order_by(Provider.name, Model.model_id)
        )
        
        models_by_provider = {}
        for model, provider in result:
            if provider.name not in models_by_provider:
                models_by_provider[provider.name] = {
                    "provider": provider,
                    "active": [],
                    "inactive": [],
                }
            
            entry = {
                "id": str(model.id),
                "model_id": model.model_id,
                "display_name": model.display_name,
                "validation_status": model.validation_status,
                "is_active": model.is_active,
            }
            if model.is_active:
                models_by_provider[provider.name]["active"].append(entry)
            else:
                models_by_provider[provider.name]["inactive"].append(entry)
        
        print("\n" + "="*100)
        print("MODEL INVENTORY BY PROVIDER")
        print("="*100)
        
        for provider_name in sorted(models_by_provider.keys()):
            data = models_by_provider[provider_name]
            active = data["active"]
            inactive = data["inactive"]
            total = len(active) + len(inactive)
            
            print(f"\n📦 {provider_name.upper()} - {len(active)} active, {len(inactive)} inactive (total: {total})")
            print("-" * 100)
            
            if active:
                print("  ACTIVE MODELS:")
                for m in active[:10]:  # Show first 10
                    status_badge = "✓" if m["validation_status"] == "validated" else "⚠"
                    print(f"    {status_badge} {m['model_id']:<40} [{m['validation_status']}]")
                if len(active) > 10:
                    print(f"    ... and {len(active) - 10} more")
            
            if inactive:
                print(f"  INACTIVE MODELS: {len(inactive)} (marked unavailable)")
        
        print("\n" + "="*100)


async def cleanup_and_resync():
    """Wipe all models and perform fresh sync from catalogs."""
    async with AsyncSessionLocal() as session:
        # Get counts before
        result = await session.execute(select(Model))
        models_before = len(list(result.scalars().all()))
        
        print("\n" + "⚠️ " * 40)
        print("DESTRUCTIVE OPERATION: Deleting all models from database")
        print("⚠️ " * 40)
        print(f"\nModels in DB: {models_before}")
        print("This will delete all {0} models and perform a fresh sync.".format(models_before))
        print("\nReferences in personas, agents, and logs will be set to NULL.")
        
        response = input("\n⛔ Are you SURE you want to proceed? (type 'yes' to confirm): ")
        if response.strip().lower() != "yes":
            print("Cleanup cancelled.")
            return
        
        logger.warning(f"=== DESTRUCTIVE MODEL CLEANUP STARTING ===")
        print("\n[1/3] Deleting all models...")
        
        # Delete all models
        result = await session.execute(delete(Model))
        deleted_count = result.rowcount
        print(f"  ✓ Deleted {deleted_count} models")
        
        # Reset providers
        print("[2/3] Resetting provider configuration...")
        result_providers = await session.execute(select(Provider))
        for provider in result_providers.scalars().all():
            provider.config = {}
            provider.is_active = True
        await session.flush()
        print(f"  ✓ Reset {len(list(result_providers.scalars().all()))} providers")
        
        print("[3/3] Running fresh sync from provider catalogs...")
        try:
            sync_result = await run_model_sync(session, deduplicate_existing=False)
            await session.commit()
            
            print(f"\n" + "="*100)
            print("✓ CLEANUP AND RESYNC COMPLETE")
            print("="*100)
            print(f"Deleted:     {deleted_count} old models")
            print(f"Added:       {len(sync_result['added'])} fresh models")
            print(f"Ollama:      {sync_result['ollama_models']} models")
            print(f"Paid APIs:   {sync_result['paid_models']} models")
            
            if sync_result['provider_details']:
                print(f"\nPer-Provider Summary:")
                for prov, details in sync_result['provider_details'].items():
                    if details.get('configured'):
                        status = "✓ ACTIVE" if details.get('configured') else "✗ INACTIVE"
                        print(f"  • {prov:20} {status:12} | Discovered: {details['discovered']:3} | Added: {details['added']:3} | Deprecated: {details['deprecated_skipped']:3}")
                    else:
                        print(f"  • {prov:20} ✗ NOT CONFIGURED (no API key)")
            
            print(f"\nErrors: {len(sync_result['errors'])}")
            if sync_result['errors']:
                for err in sync_result['errors']:
                    print(f"  ! {err}")
            
            print("\n" + "="*100)
            
        except Exception as e:
            logger.error(f"Fresh sync failed: {e}")
            await session.rollback()
            print(f"\n❌ Error during fresh sync: {e}")
            print(f"But cleanup succeeded - {deleted_count} models were deleted.")
            sys.exit(1)


async def run_sync_only():
    """Run sync without deleting existing models (upsert mode)."""
    async with AsyncSessionLocal() as session:
        print("\n[*] Running standard model sync (upsert mode)...")
        print("    This will ADD new models and UPDATE existing ones, but NOT delete.")
        
        sync_result = await run_model_sync(session, deduplicate_existing=True)
        await session.commit()
        
        print(f"\n" + "="*100)
        print("✓ MODEL SYNC COMPLETE")
        print("="*100)
        print(f"Added:       {len(sync_result['added'])} new models")
        print(f"Skipped:     {sync_result['skipped_existing']} already existing")
        print(f"Ollama:      {sync_result['ollama_models']} models")
        print(f"Paid APIs:   {sync_result['paid_models']} models")
        print(f"Deactivated: (models no longer in provider catalogs)")
        
        if sync_result['provider_details']:
            print(f"\nPer-Provider Summary:")
            for prov, details in sync_result['provider_details'].items():
                if details.get('configured'):
                    status = "✓ ACTIVE" if details.get('configured') else "✗ INACTIVE"
                    print(f"  • {prov:20} {status:12} | Discovered: {details['discovered']:3} | Added: {details['added']:3} | Deactivated: {details['deactivated']:3}")
                else:
                    print(f"  • {prov:20} ✗ NOT CONFIGURED (no API key)")
        
        print(f"\nErrors: {len(sync_result['errors'])}")
        if sync_result['errors']:
            for err in sync_result['errors']:
                print(f"  ! {err}")
        
        print("\n" + "="*100)


async def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    try:
        if command == "status":
            await show_status()
        elif command == "cleanup":
            await cleanup_and_resync()
        elif command == "sync":
            await run_sync_only()
        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
