from flask import Flask, send_file, request, jsonify
from elasticsearch import Elasticsearch

es = Elasticsearch(
    [{'host': 'localhost', 'port': 9200, 'scheme': 'http'}],
    http_auth=('Abdullah', 'Abdullah')
)

index_name = "reuters_news_index"

def get_top_georeferences(index_name):
    aggregation_query = {
        "size": 10,
        "aggs": {
            "top_georeferences": {
                "terms": {
                    "field": "Georeferences.keyword",
                    "size": 10
                }
            }
        }
    }

    try:
        results = es.search(index=index_name, body=aggregation_query)
        top_georeferences = []

        if 'aggregations' in results:
            nested_aggregation = results['aggregations'].get('top_georeferences', {})
            if 'buckets' in nested_aggregation:
                buckets = nested_aggregation['buckets']
                top_georeferences = [{"key": nested_bucket['key'], "doc_count": nested_bucket['doc_count']} for nested_bucket in buckets]

        return top_georeferences

    except Exception as e:
        print(f"An error occurred: {e}")
        return []

def search_documents(query, temporal_expression, georeference):
    search_body = {
        "_source": ["Title", "Content", "Date", "Georeferences"],
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": ["Title^2", "Content"]
                    }
                },
                "should": [
                    {
                        "match": {
                        "TemporalExpressions": temporal_expression
                        }
                    },
                    {
                            "match": {
                                "Georeferences.name": georeference
                            }
                    }
                ],
                "minimum_should_match": 1,
            }
        },
        "sort": [
            "_score"
        ]
    }

    results = es.search(index=index_name, body=search_body)

    relevant_documents = []

    for hit in results['hits']['hits']:
        document = {
            'Title': hit['_source']['Title'],
            'Content': hit['_source']['Content'],
            'Date': hit['_source']['Date'],
            'Georeferences': hit['_source']['Georeferences']
        }
    relevant_documents.append(document)


    return relevant_documents


app = Flask(__name__)

@app.route("/")
def main():
    return send_file('index.html')


@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('query')

    if len(query) < 3:
        return jsonify(suggestions=[])

    search_body = {
        "query": {
            "bool": {
                "should": [
                    {
                        "fuzzy": {
                            "Title": {
                                "value": query.lower(),
                                "fuzziness": "AUTO",
                                "prefix_length": 0,
                                "max_expansions": 10
                            }
                        }
                    },
                    {
                        "match_phrase": {
                            "Title": {
                                "query": query
                            }
                        }
                    },
                    {
                        "wildcard": {
                            "Title": {
                                "value": f"*{query.lower()}*"
                            }
                        }
                    },
                ],
                "minimum_should_match": 1
            }
        }
    }

    results = es.search(index=index_name, body=search_body)

    suggestions = [hit['_source']['Title'] for hit in results['hits']['hits']]

    return jsonify(suggestions=suggestions)


@app.route('/search', methods=['POST'])
def search():
    data = request.json

    query = data.get('query')
    temporal_expression = data.get('TemporalExpressions')
    georeference = data.get('Georeferences')

    if not query:
        return jsonify({"error": "Missing 'query' parameter"}), 400

    results = search_documents(query, temporal_expression, georeference)

    return jsonify({"results": results})


@app.route('/top_georeferences', methods=['GET'])
def top_georeferences():
    result = get_top_georeferences(index_name)
    return jsonify(result)


@app.route('/distribution', methods=['GET'])
def document_distribution_over_time():

    aggregation_query = {
        "size": 0,
        "aggs": {
            "documents_over_time": {
                "date_histogram": {
                    "field": "Date", 
                    "fixed_interval": "1d", 
                    "format": "yyyy-MM-dd"
                }
            }
        }
    }

    try:
        results = es.search(index=index_name, body=aggregation_query)
        buckets = results['aggregations']['documents_over_time']['buckets']

        distribution_over_time = [{"date": bucket['key_as_string'], "doc_count": bucket['doc_count']} for bucket in buckets]

        return jsonify({"document_distribution_over_time": distribution_over_time})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
