from models.news_item import NewsItem
from flask import *
from openai import OpenAI
import json, time
import requests
from dotenv import load_dotenv
import os

app = Flask(__name__)

# Enable CORS so the frontend (served from a different origin, e.g. a static
# server or file://) can call this API from the browser. Done manually via an
# after_request hook so it works without the flask_cors package installed.
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# Load environment variables
def configure():
    load_dotenv()

# Route for the home page
@app.route('/', methods = ['GET'])
def home_page():
    # Create a JSON-formatted response for the home page with a welcome message and timestamp
    data_set = {'Page': 'Home', 'Message': 'Welcome to Stock App Page', 'TimeStamp': time.time()}
    json_dump = json.dumps(data_set)

    return json_dump

# Route for the stock sentiment page
@app.route('/sentiment/', methods = ['GET'])
def requests_page():
    # Retrieve the query parameters 'ticker' and 'limit' to determine which stocks to analyze and how many news articles to retrieve
    ticker = request.args.get('ticker')
    limit = request.args.get('limit', 10)
    
    # Construct the URL to make the GET request to Polygon API to retrieve the latest news for the specified stock
    url = "https://api.polygon.io/v2/reference/news?ticker={0}&limit={1}&apiKey={2}".format(ticker, limit, os.getenv('polygon_api_key'))
    
    # GET request to retrieve the latest stock news for the specified ticker
    stock_news_data = requests.get(url)
    
    # Convert the response object into a JSON-formatted string
    stock_news_json = stock_news_data.json()

    # Extract the news data from the JSON-formatted response and format it into a list of news item objects
    results = stock_news_json.get('results')

    # Guard against an empty/missing result set (e.g. invalid ticker or no recent news)
    if not results:
        return jsonify({
            "error": "No news results found for ticker '{0}'. Check the symbol and try again.".format(ticker),
            "sentiments": []
        }), 404

    data_model = []
    for result in results:
        item = NewsItem(
            id = result.get('id'),
            publisher = result.get('publisher').get('name'),
            title = result.get('title'),
            author = result.get('author'),
            published_utc = result.get('published_utc'),
            article_url = result.get('article_url'),
            tickers = result.get('tickers'),
            image_url = result.get('image_url'),
            description = result.get('description'),
            keywords = result.get('keywords')
        )
        data_model.append(item)
    
    # Pass the news data to the following function to generate a sentiment analysis
    ai_stock_sentiment = analyse_stock_news(user_input = results)

    print(ai_stock_sentiment)

    return ai_stock_sentiment


def analyse_stock_news(user_input):
    # Construct a prompt for the GPT-3.5 model using the input stock news data
    prompt = f"""
    {user_input}
    Analyse the sentiment of the stocks from the following json {user_input} and return a JSON array as result
    Provide sentiment on a scale of 1-100
    Provide recommendation for the stock
    Provide a reason for the recommendation
    Provide the sources for reason, recommendation and sentiment
    The JSON must have these fields: sentiment, sentiment_score.
    """
    
    # Initialize the OpenAI API client
    client = OpenAI(api_key=os.getenv('openai_api_key'))

    # JSON schema for the structured response. Every property is required and
    # additionalProperties is false, as mandated by OpenAI structured outputs.
    sentiment_schema = {
        "type": "object",
        "properties": {
            "sentiments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "description": "Symbol used to represent the stock"},
                        "stock_name": {"type": "string", "description": "Full name of the stock"},
                        "sentiment_score": {"type": "integer", "description": "Score between 1-100 of the sentiment"},
                        "recommendation": {"type": "string", "description": "Choose between Strongly Bullish, Bullish, Neutral and Bearish to recommend suggestion for buying stock"},
                        "reason": {"type": "string", "description": "Provide reasons for the recommendation and the sentiment_score"},
                        "source": {"type": "string", "description": "Quote the source or web url link for the reason and recommendation"},
                    },
                    "required": ["ticker", "stock_name", "sentiment_score", "recommendation", "reason", "source"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["sentiments"],
        "additionalProperties": False,
    }

    # Make the API call using the current structured-outputs pattern (response_format
    # with a strict json_schema) instead of the deprecated functions= parameter.
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful review analysis tool."},
            {"role": "user", "content": prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "stock_sentiments",
                "strict": True,
                "schema": sentiment_schema,
            },
        },
    )

    # With structured outputs the content is a JSON string matching the schema.
    try:
        generated_text = completion.choices[0].message.content
        return json.loads(generated_text)
    except Exception as e:
        print(f"An error occurred: {e}")
        return None
    

if __name__ == '__main__':
    # Load environment variables
    configure()
    
    # Begins listening for incoming requests on port 8888
    app.run(port = 8888)
