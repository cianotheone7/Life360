# Scripts Directory

This directory contains utility scripts for database migrations, data cleanup, and one-time operations.

## Script Categories

### Stock Management Scripts
- `add_*.py` - Scripts to add stock items to the database
- `delete_*.py` - Scripts to delete stock items
- `update_*.py` - Scripts to update stock item information

### Data Migration Scripts
- `migrate_*.py` - Database schema migration scripts
- `fix_*.py` - Data correction scripts

### Cleanup Scripts
- `cleanup_*.py` - Data cleanup and maintenance scripts

### Utility Scripts
- `check_*.py` - Data validation and checking scripts
- `setup_azure_github_secrets.py` - Helper script for setting up Azure credentials (one-time use)

## Usage

Most of these scripts are one-time use scripts that were run during initial setup or migrations. They are kept here for reference.

To run a script:
```bash
python scripts/script_name.py
```

**Note:** Make sure you have the correct `DATABASE_URL` environment variable set before running scripts that interact with the database.

