#!/usr/bin/env python3
"""
Azure Function for WooCommerce Sync
This can be deployed as an Azure Function and triggered by a timer
"""
import azure.functions as func
import requests
import json
import logging
from datetime import datetime

def main(mytimer: func.TimerRequest) -> None:
    """
    Azure Function that triggers WooCommerce sync every 30 seconds
    
    To deploy this as an Azure Function:
    1. Create a new Azure Function App
    2. Set up a Timer Trigger with schedule: "*/30 * * * * *" (every 30 seconds)
    3. Add your Flask app URL as an environment variable: FLASK_APP_URL
    4. Deploy this function
    """
    
    utc_timestamp = datetime.utcnow().replace(
        tzinfo=None
    ).isoformat()

    if mytimer.past_due:
        logging.info('The timer is past due!')

    # Get your Flask app URL from environment variables
    import os
    flask_app_url = os.environ.get('FLASK_APP_URL', 'https://your-app.azurewebsites.net')
    
    try:
        # Call your Flask app's sync endpoint
        sync_url = f"{flask_app_url}/api/woocommerce/sync"
        
        response = requests.post(sync_url, 
                               json={'days_back': 0.042},  # 1 hour
                               timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('new_orders', 0) > 0 or result.get('updated_orders', 0) > 0:
                logging.info(f'Sync successful: {result["message"]}')
            else:
                logging.info('Sync completed - no new orders')
        else:
            logging.error(f'Sync failed with status {response.status_code}: {response.text}')
            
    except Exception as e:
        logging.error(f'Error during sync: {str(e)}')

    logging.info(f'Python timer trigger function ran at {utc_timestamp}')


# Alternative: Azure Logic App HTTP trigger version
def main_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP version for Azure Logic Apps
    This can be called by Azure Logic Apps on a schedule
    """
    try:
        # Get your Flask app URL from environment variables
        import os
        flask_app_url = os.environ.get('FLASK_APP_URL', 'https://your-app.azurewebsites.net')
        
        # Call your Flask app's sync endpoint
        sync_url = f"{flask_app_url}/api/woocommerce/sync"
        
        response = requests.post(sync_url, 
                               json={'days_back': 0.042},  # 1 hour
                               timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return func.HttpResponse(
                json.dumps(result),
                status_code=200,
                mimetype="application/json"
            )
        else:
            return func.HttpResponse(
                json.dumps({"error": f"Sync failed: {response.text}"}),
                status_code=500,
                mimetype="application/json"
            )
            
    except Exception as e:
        return func.HttpResponse(
            json.dumps({"error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )

