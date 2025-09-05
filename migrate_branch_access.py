#!/usr/bin/env python3
"""
Migration script to update existing users' branch access from NULL to empty list

This script will:
1. Find all users with NULL accessible_branch_ids
2. Update them to have empty list [] (which means access to all branches)
3. Show a summary of changes made

Run this script after adding the accessible_branch_ids column to your database.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import app
from models import User
from extensions import db

def migrate_branch_access():
    """Migrate NULL accessible_branch_ids to empty list"""
    with app.app_context():
        try:
            print("🔄 Starting branch access migration...")
            
            # Find users with NULL accessible_branch_ids
            users_with_null = User.query.filter(User.accessible_branch_ids.is_(None)).all()
            
            print(f"📊 Found {len(users_with_null)} users with NULL branch access")
            
            if len(users_with_null) == 0:
                print("✅ No users need migration. All users already have proper branch access values.")
                return
            
            # Show users that will be updated
            print("\n👥 Users to be updated:")
            for user in users_with_null:
                print(f"  - {user.firstname} {user.lastname} ({user.email}) - Role: {user.role}")
            
            # Confirm migration
            response = input(f"\n❓ Do you want to update these {len(users_with_null)} users? (y/N): ")
            if response.lower() != 'y':
                print("❌ Migration cancelled.")
                return
            
            # Update users
            updated_count = 0
            for user in users_with_null:
                try:
                    user.accessible_branch_ids = []  # Empty list = access to all branches
                    updated_count += 1
                    print(f"✅ Updated: {user.firstname} {user.lastname}")
                except Exception as e:
                    print(f"❌ Error updating {user.firstname} {user.lastname}: {e}")
            
            # Commit changes
            try:
                db.session.commit()
                print(f"\n🎉 Migration completed successfully!")
                print(f"📈 Updated {updated_count} users")
                print("💡 Empty list [] now means 'access to all branches'")
                
                # Show final summary
                print("\n📊 Final branch access summary:")
                all_users = User.query.all()
                null_count = User.query.filter(User.accessible_branch_ids.is_(None)).count()
                empty_list_count = User.query.filter(User.accessible_branch_ids == []).count()
                specific_access_count = User.query.filter(
                    User.accessible_branch_ids.isnot(None),
                    User.accessible_branch_ids != []
                ).count()
                
                print(f"  - NULL values: {null_count}")
                print(f"  - Empty list [] (all branches): {empty_list_count}")
                print(f"  - Specific branch access: {specific_access_count}")
                print(f"  - Total users: {len(all_users)}")
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error committing changes: {e}")
                print("🔄 Changes have been rolled back.")
                
        except Exception as e:
            print(f"❌ Error during migration: {e}")
            import traceback
            traceback.print_exc()

def show_current_status():
    """Show current branch access status"""
    with app.app_context():
        try:
            print("📊 Current Branch Access Status:")
            print("=" * 50)
            
            all_users = User.query.all()
            null_count = User.query.filter(User.accessible_branch_ids.is_(None)).count()
            empty_list_count = User.query.filter(User.accessible_branch_ids == []).count()
            specific_access_count = User.query.filter(
                User.accessible_branch_ids.isnot(None),
                User.accessible_branch_ids != []
            ).count()
            
            print(f"Total users: {len(all_users)}")
            print(f"NULL values: {null_count}")
            print(f"Empty list [] (all branches): {empty_list_count}")
            print(f"Specific branch access: {specific_access_count}")
            
            if null_count > 0:
                print(f"\n⚠️  {null_count} users still have NULL values and need migration.")
            else:
                print("\n✅ All users have proper branch access values.")
                
        except Exception as e:
            print(f"❌ Error checking status: {e}")

if __name__ == "__main__":
    print("🔧 Branch Access Migration Tool")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        show_current_status()
    else:
        print("This script will update users with NULL accessible_branch_ids to empty list []")
        print("Empty list [] means 'access to all branches'")
        print("\nOptions:")
        print("  python migrate_branch_access.py        - Run migration")
        print("  python migrate_branch_access.py status - Show current status")
        print()
        
        migrate_branch_access()
