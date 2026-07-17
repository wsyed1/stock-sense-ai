import requests
from bs4 import BeautifulSoup
from flask import *
from openai import OpenAI
import json, time
import requests

app = Flask(__name__)

# Initialize OpenAI API key (make sure to replace "your-api-key" with your actual API key)
# openai.api_key = "your-api-key"

@app.route('/scrapper/', methods = ['GET'])
def scrape_webpage():
    # Send a GET request to the URL
    response = requests.get("https://www.fool.com/investing/2024/08/02/why-nvidia-stock-kept-tumbling-on-friday/?source=iedfolrf0000001")

    # Check if the request was successful
    if response.status_code != 200:
        raise Exception(f"Failed to fetch the webpage: {response.status_code}")
    
    # Parse the HTML content using BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    print("***********")
    print(soup)
    # Find the main content part of the article (this may need customization based on the website structure)
    article_body = soup.find('div', class_='article-content')  # This class name is an example; use the correct one for your webpage

    if not article_body:
        raise Exception("Failed to find the article content on the page")

    # Extract text from the article body
    article_text = article_body.get_text(separator='\n', strip=True)
    
    return article_text

# def analyze_text(text):
#     # Use OpenAI's GPT-4 model to analyze the text
#     try:
#         response = openai.Completion.create(
#             engine="text-davinci-002",  # Ensure that "text-davinci-002" or the model you want to use is supported
#             prompt=f"Analyze the following news article:\n\n{text}",
#             max_tokens=300,
#             temperature=0.7
#         )
#         analysis = response.choices[0].text.strip()
#         return analysis
#     except openai.error.OpenAIError as e:
#         raise Exception(f"Error during OpenAI API call: {e}")

# # Define the URL of the news article
# url = "https://www.fool.com/investing/2024/08/02/why-nvidia-stock-kept-tumbling-on-friday/?source=iedfolrf0000001"

# # Scrape data from the webpage
# article_text = scrape_webpage(url)

# # Analyze the scraped text using AI
# analysis = analyze_text(article_text)

# # Print the analysis
# print(analysis)

if __name__ == '__main__':
    app.run(port = 8888)