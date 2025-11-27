# Save as: E:\FreshiFy_Mobile_App_Backend\test_mongodb.py
"""
Quick MongoDB Connection Test for FreshiFy Backend
Run this to diagnose MongoDB Atlas connection issues
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

print("=" * 70)
print("FreshiFy MongoDB Connection Test")
print("=" * 70)

# Check environment variables
print("\n1. Environment Check:")
print("-" * 70)
mongo_uri = os.getenv("MONGODB_URI")
db_name = os.getenv("DB_NAME", "DB_FreshiFy")

if not mongo_uri:
    print("❌ MONGODB_URI not found in .env file")
    sys.exit(1)

print(f"✓ MONGODB_URI: {mongo_uri[:50]}...")
print(f"✓ DB_NAME: {db_name}")

# Check Python packages
print("\n2. Python Packages Check:")
print("-" * 70)

packages = {
    "pymongo": None,
    "certifi": None,
    "dnspython": None,
}

for pkg_name in packages:
    try:
        if pkg_name == "dnspython":
            import dns.resolver
            pkg = dns.resolver
        else:
            pkg = __import__(pkg_name)
        version = getattr(pkg, "__version__", "unknown")
        packages[pkg_name] = version
        print(f"✓ {pkg_name:12} : v{version}")
    except ImportError:
        print(f"❌ {pkg_name:12} : NOT INSTALLED")
        packages[pkg_name] = None

# Check if required packages are installed
if not packages["pymongo"]:
    print("\n❌ pymongo is required. Install with:")
    print("   pip install 'pymongo[srv]'")
    sys.exit(1)

if not packages["dnspython"]:
    print("\n⚠ dnspython required for mongodb+srv://")
    print("   pip install 'pymongo[srv]'")

# Test connection
print("\n3. MongoDB Connection Test:")
print("-" * 70)

try:
    from pymongo import MongoClient
    from pymongo.errors import ServerSelectionTimeoutError, ConfigurationError
    
    # Test 1: Basic connection with certifi
    print("\nTest 1: Standard connection with certifi...")
    try:
        import certifi
        client = MongoClient(
            mongo_uri,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=10000
        )
        client.admin.command('ping')
        print("✓ SUCCESS with certifi!")
        
        # List databases
        dbs = client.list_database_names()
        print(f"✓ Available databases: {dbs}")
        
        # Check FreshiFy database
        if db_name in dbs:
            db = client[db_name]
            collections = db.list_collection_names()
            print(f"✓ Collections in {db_name}: {collections}")
        else:
            print(f"⚠ Database '{db_name}' not found (will be created on first insert)")
        
        client.close()
        print("\n✅ MongoDB connection is WORKING!")
        sys.exit(0)
        
    except Exception as e:
        print(f"❌ Failed: {type(e).__name__}")
        print(f"   {str(e)[:200]}")
    
    # Test 2: With tlsAllowInvalidCertificates
    print("\nTest 2: Connection with tlsAllowInvalidCertificates...")
    try:
        client = MongoClient(
            mongo_uri + "&tls=true&tlsAllowInvalidCertificates=true",
            serverSelectionTimeoutMS=10000
        )
        client.admin.command('ping')
        print("✓ SUCCESS with tlsAllowInvalidCertificates!")
        print("\n⚠ Warning: This bypasses SSL validation.")
        print("   For production, fix your SSL certificates instead.")
        client.close()
        sys.exit(0)
    except Exception as e:
        print(f"❌ Failed: {type(e).__name__}")
        print(f"   {str(e)[:200]}")
    
    # Test 3: Check network connectivity
    print("\nTest 3: Network connectivity check...")
    try:
        import socket
        host = "cluster0.ngoq3yd.mongodb.net"
        port = 27017
        socket.create_connection((host, port), timeout=5)
        print(f"✓ Can reach {host}:{port}")
    except Exception as e:
        print(f"❌ Cannot reach MongoDB servers: {e}")
        print("   Possible causes:")
        print("   - Firewall blocking connection")
        print("   - VPN/proxy interfering")
        print("   - MongoDB Atlas IP whitelist")
    
    print("\n" + "=" * 70)
    print("DIAGNOSIS FAILED")
    print("=" * 70)
    print("\nTroubleshooting Steps:")
    print("1. Update packages: pip install --upgrade pymongo certifi")
    print("2. Check MongoDB Atlas IP whitelist (add 0.0.0.0/0 for testing)")
    print("3. Verify credentials in .env file")
    print("4. Check if antivirus/firewall is blocking port 27017")
    print("5. Try connecting from MongoDB Compass GUI")
    print("=" * 70)
    
except ImportError as e:
    print(f"\n❌ Import error: {e}")
    print("   Install required packages:")
    print("   pip install 'pymongo[srv]' certifi")
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")

sys.exit(1)