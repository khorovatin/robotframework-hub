"""
This provides the view functions for the /api/keywords endpoints
"""
from typing import Any, Dict

import flask
from flask import Blueprint, abort, current_app, jsonify, request, url_for
from robot.utils import html_format


class ApiEndpoint:
    """
    Manages the API endpoints for retrieving keyword documentation.
    """
    def __init__(self, blueprint: Blueprint) -> None:
        """
        Registers URL rules for the keyword-related API endpoints.

        :param blueprint: The Flask Blueprint to attach the routes to.
        """
        blueprint.add_url_rule("/keywords/", view_func=self.get_keywords)
        blueprint.add_url_rule("/keywords/<collection_id>", view_func=self.get_library_keywords)
        blueprint.add_url_rule("/keywords/<collection_id>/<keyword>", view_func=self.get_library_keyword)

    def get_library_keywords(self, collection_id: str) -> flask.Response:
        """
        Retrieves a list of keywords for a given collection, with optional
        filtering by pattern and requested fields.

        :param collection_id: The unique identifier for the library collection.
        :return: A Flask JSON response containing the list of keywords.
        """
        query_pattern = request.args.get('pattern', "*").strip().lower()
        # Why: Fetches raw keyword data from the keyword database (kwdb).
        kwdb = getattr(current_app, "kwdb", None)
        if kwdb is None:
            current_app.logger.error("The 'kwdb' attribute is not set on the Flask app instance.")
            abort(500, description="Internal server error: keyword database not configured.")
        keywords = kwdb.get_keywords(query_pattern)

        req_fields = request.args.get('fields', "*").strip().lower()
        all_fields = ("collection_id", "library", "name", "synopsis", "doc", "htmldoc",
                    "args", "doc_keyword_url", "api_keyword_url", "api_library_url")

        # Why: Determine which fields to include in the response. If the user
        # requests "*", all fields are returned.
        fields_to_include = all_fields if req_fields == "*" else [
            field.strip() for field in req_fields.split(",")
        ]

        result = []
        for (keyword_collection_id, keyword_collection_name,
            keyword_name, keyword_doc, keyword_args) in keywords:

            if collection_id == "" or collection_id == keyword_collection_id:
                data: Dict[str, Any] = {}

                # Why: This dictionary maps field names to the values we have,
                # making the construction of the response data cleaner.
                field_mapping = {
                    "collection_id": keyword_collection_id,
                    "library": keyword_collection_name,
                    "name": keyword_name,
                    "synopsis": keyword_doc.strip().split("\n")[0],
                    "doc": keyword_doc,
                    "args": keyword_args,
                    "doc_keyword_url": url_for("doc.doc_for_library", collection_id=keyword_collection_id, keyword=keyword_name),
                    "api_keyword_url": url_for(".get_library_keyword", collection_id=keyword_collection_id, keyword=keyword_name),
                    "api_library_url": url_for(".get_library_keywords", collection_id=keyword_collection_id)
                }

                for field in fields_to_include:
                    if field in field_mapping:
                        data[field] = field_mapping[field]

                    # Why: Use the stable `html_format` public API to convert Robot doc
                    # syntax into HTML. This replaces the old, internal DocToHtml class.
                    elif field == "htmldoc":
                        try:
                            data["htmldoc"] = html_format(keyword_doc)
                        except Exception as e:
                            # Why: If formatting fails, log the error and return an empty
                            # string to prevent the entire request from failing.
                            current_app.logger.error(f"Failed to generate htmldoc for '{keyword_name}': {e}")
                            data["htmldoc"] = f"<p>Error generating documentation: {e}</p>"

                result.append(data)

        return jsonify(keywords=result)

    def get_keywords(self) -> flask.Response:
        """
        A convenience endpoint to get keywords, defaulting to all collections.
        """
        # Why: This allows the /keywords/ endpoint to function as a search
        # across all collections by delegating to get_library_keywords.
        collection_id = request.args.get('collection_id', "")
        return self.get_library_keywords(collection_id)

    def get_library_keyword(self, collection_id: str, keyword: str) -> flask.Response:
        """
        Retrieves detailed information for a single, specific keyword.

        :param collection_id: The unique identifier for the library collection.
        :param keyword: The name of the keyword to retrieve.
        :return: A Flask JSON response with the keyword's details or a 404 error.
        """
        kwdb = getattr(current_app, "kwdb", None)
        if kwdb is None:
            current_app.logger.error("The 'kwdb' attribute is not set on the Flask app instance.")
            abort(500, description="Internal server error: keyword database not configured.")

        # Why: The collection_id could be a name or an ID. If it's a name that
        # resolves to a single collection, we use its canonical ID.
        collections = kwdb.get_collections(pattern=collection_id.strip().lower())
        if len(collections) == 1:
            collection_id = collections[0]["collection_id"]
        elif len(collections) > 1:
            # Why: The provided name is ambiguous and matches multiple collections.
            abort(404, description="Ambiguous collection identifier.")

        try:
            keyword_data = kwdb.get_keyword(collection_id, keyword)
        except Exception as e:
            current_app.logger.warning(f"Error fetching keyword '{keyword}' from collection '{collection_id}': {e}")
            abort(404, description="Keyword not found or database error.")

        if keyword_data:
            keyword_data["library_url"] = url_for(".get_library", collection_id=keyword_data["collection_id"])
            return jsonify(keyword=keyword_data)

        # Why: If the database returns no data for the keyword, it doesn't exist.
        abort(404, description="Keyword not found.")

