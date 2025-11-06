"""
Script to create Azure Service Principal for GitHub Actions deployment
Run this script to generate credentials for GitHub Secrets
"""
import subprocess
import json
import sys

# Azure details
RESOURCE_GROUP = "life360-2578617155"
SUBSCRIPTION_ID = None  # Will be detected automatically
SERVICE_PRINCIPAL_NAME = "life360-github-actions"

def run_command(cmd):
    """Run a command and return the output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {cmd}")
        print(f"Error: {e.stderr}")
        return None

def get_subscription_id():
    """Get the current Azure subscription ID"""
    output = run_command("az account show --query id -o tsv")
    if output:
        return output
    return None

def create_service_principal():
    """Create Azure Service Principal for GitHub Actions"""
    print("=" * 60)
    print("Creating Azure Service Principal for GitHub Actions")
    print("=" * 60)
    
    # Get subscription ID
    sub_id = get_subscription_id()
    if not sub_id:
        print("Error: Could not get Azure subscription ID")
        print("Please run: az login")
        return False
    
    print(f"\nSubscription ID: {sub_id}")
    
    # Create service principal with contributor role
    print(f"\nCreating service principal: {SERVICE_PRINCIPAL_NAME}...")
    
    cmd = f'''az ad sp create-for-rbac --name "{SERVICE_PRINCIPAL_NAME}" --role contributor --scopes /subscriptions/{sub_id}/resourceGroups/{RESOURCE_GROUP} --sdk-auth'''
    
    output = run_command(cmd)
    
    if not output:
        print("Error: Failed to create service principal")
        return False
    
    try:
        credentials = json.loads(output)
        
        print("\n" + "=" * 60)
        print("SUCCESS! Add this JSON to GitHub Secrets")
        print("=" * 60)
        print("\n1. Go to: https://github.com/cianotheone7/Life360/settings/secrets/actions")
        print("2. Click 'New repository secret'")
        print("3. Name: AZURE_CREDENTIALS")
        print("4. Value: (paste the JSON below)")
        print("\n" + "-" * 60)
        print(json.dumps(credentials, indent=2))
        print("-" * 60)
        
        print("\n" + "=" * 60)
        print("Alternative: Manual Setup")
        print("=" * 60)
        print("\nIf the above doesn't work, you can also create it manually:")
        print(f"az ad sp create-for-rbac --name \"{SERVICE_PRINCIPAL_NAME}\" \\")
        print(f"  --role contributor \\")
        print(f"  --scopes /subscriptions/{sub_id}/resourceGroups/{RESOURCE_GROUP} \\")
        print("  --sdk-auth")
        
        return True
        
    except json.JSONDecodeError:
        print("Error: Could not parse service principal output")
        print("Output:", output)
        return False

if __name__ == "__main__":
    print("\nThis script will create an Azure Service Principal for GitHub Actions.")
    print("Make sure you are logged in to Azure CLI (az login)\n")
    
    response = input("Continue? (y/n): ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        sys.exit(0)
    
    success = create_service_principal()
    
    if success:
        print("\n✅ Service principal created successfully!")
        print("\nNext steps:")
        print("1. Copy the JSON output above")
        print("2. Add it as a GitHub Secret named 'AZURE_CREDENTIALS'")
        print("3. Push your code to GitHub - it will auto-deploy!")
    else:
        print("\n❌ Failed to create service principal")
        sys.exit(1)


