#!/usr/bin/env python3
"""
Database seeding script for CEQ templates.
Run with: python -m ceq_api.scripts.seed_db
"""

import asyncio
import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ceq_api.db.session import async_session_maker, init_db
from ceq_api.models.template import Template
from ceq_api.seed_templates import SEED_TEMPLATES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def seed_templates(session: AsyncSession, force: bool = False) -> int:
    """
    Seed the database with initial templates.

    Args:
        session: Database session
        force: If True, recreate existing templates

    Returns:
        Number of templates created
    """
    created = 0

    for template_data in SEED_TEMPLATES:
        # Check if template already exists
        existing = await session.execute(
            select(Template).where(Template.name == template_data["name"])
        )
        existing_template = existing.scalar_one_or_none()

        if existing_template:
            if force:
                logger.info(f"Updating template: {template_data['name']}")
                for key, value in template_data.items():
                    if hasattr(existing_template, key):
                        setattr(existing_template, key, value)
            else:
                logger.info(f"Skipping existing template: {template_data['name']}")
                continue
        else:
            logger.info(f"Creating template: {template_data['name']}")
            template = Template(
                id=uuid4(),
                name=template_data["name"],
                description=template_data.get("description", ""),
                category=template_data["category"],
                workflow_json=template_data["workflow_json"],
                input_schema=template_data.get("input_schema", {}),
                tags=template_data.get("tags", []),
                thumbnail_url=template_data.get("thumbnail_url"),
                preview_urls=template_data.get("preview_urls", []),
                model_requirements=template_data.get("model_requirements", []),
                vram_requirement_gb=template_data.get("vram_requirement_gb", 8),
            )
            session.add(template)
            created += 1

    await session.commit()
    return created


async def main(force: bool = False) -> None:
    """Main entry point for seeding."""
    logger.info("Initializing database...")
    await init_db()

    logger.info("Seeding templates...")
    async with async_session_maker() as session:
        created = await seed_templates(session, force=force)
        logger.info(f"Seeding complete. Created {created} templates.")

    # Print summary
    async with async_session_maker() as session:
        result = await session.execute(select(Template))
        templates = result.scalars().all()

        logger.info("\n=== Template Summary ===")
        categories = {}
        for t in templates:
            categories.setdefault(t.category, []).append(t.name)

        for category, names in sorted(categories.items()):
            logger.info(f"\n{category.upper()} ({len(names)} templates):")
            for name in names:
                logger.info(f"  - {name}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    asyncio.run(main(force=force))
