from flask import *
from openai import OpenAI
from dotenv import load_dotenv
import os
import json, time
import requests

app = Flask(__name__)

# Load environment variables
def configure():
    load_dotenv()

# Route for the home page
@app.route('/', methods = ['GET'])
def home_page():
    data_set = {'Page': 'Home', 'Message': 'Welcome to Stock App Page', 'TimeStamp': time.time()}
    json_dump = json.dumps(data_set)

    return json_dump

# Route for the stock news analysis page
@app.route('/news/', methods = ['GET'])
def requests_page():
    limit = request.args.get('limit')
    url = "https://api.polygon.io/v2/reference/news?limit={0}&apiKey={1}".format(limit, os.getenv('polygon_api_key'))
    stock_news_data = requests.get(url)

    # Convert the response object into a JSON-formatted string
    stock_news_json = stock_news_data.json()

    # Convert the Python dictionary back into a formatted JSON-formatted string
    json_dump = json.dumps(stock_news_json)

    # Pass the JSON-formatted string to the following method to generate stock analysis
    ai_news_analysis = get_news_openai(json_stock_news=json_dump)

    print(ai_news_analysis)
    
    return ai_news_analysis

# Function that generates an analysis of the stocks based on the latest news data
def get_news_openai(json_stock_news):
    client = OpenAI(api_key=os.getenv('openai_api_key'))
    prompt="Generate an analysis of the stocks based on the following data {0}.".format(json_stock_news)

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
            ],
        # max_tokens=50
    )
    
    # Return the content of the response generated by the GPT model
    return response.choices[0].message.content

if __name__ == '__main__':
    # Load environment variables
    configure()
    # Begins listening for incoming requests on port 8888
    app.run(port = 8888)