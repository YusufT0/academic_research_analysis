"""Quick test script for database statistics"""
import asyncio
from database import init_database_service, close_database
from database.models import Journal, Issue, Article
from database.connection import get_database


async def test():
    svc = await init_database_service()
    db = get_database()
    
    # Direct counts - Beanie 2.x syntax
    j = await Journal.find().count()
    i = await Issue.find().count()
    a = await Article.find().count()
    
    print(f"\n=== Direct Model Counts (find().count()) ===")
    print(f"Journal: {j}")
    print(f"Issue: {i}")
    print(f"Article: {a}")
    
    # Manual get_statistics test
    print(f"\n=== Manual get_statistics test ===")
    try:
        stats = await db.database.command("dbstats")
        print(f"dbstats OK: collections={stats.get('collections')}")
        
        jc = await Journal.find().count()
        print(f"Journal.find().count() = {jc}")
        
        ic = await Issue.find().count()
        print(f"Issue.find().count() = {ic}")
        
        ac = await Article.find().count()
        print(f"Article.find().count() = {ac}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    # Database statistics
    db_stats = await db.get_statistics()
    print(f"\n=== DB get_statistics() return value ===")
    print(f"Full result: {db_stats}")
    
    # Journal repo statistics
    journal_stats = await svc.journal_repo.get_statistics_by_source()
    print(f"\n=== Journal Repo get_statistics_by_source() ===")
    for stat in journal_stats:
        print(f"  {stat['_id']}: journals={stat.get('total_journals')}, issues={stat.get('total_issues')}, articles={stat.get('total_articles')}")
    
    await close_database()


if __name__ == "__main__":
    asyncio.run(test())
