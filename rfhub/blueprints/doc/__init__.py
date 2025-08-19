"""Flask blueprint for showing keyword documentation"""

import io
import json

import flask
from flask import current_app
from robot.libdocpkg.htmlutils import DocToHtml

from rfhub.version import __version__

blueprint = flask.Blueprint(
    "doc", __name__, template_folder="templates", static_folder="static"
)


@blueprint.route('/')
@blueprint.route("/keywords/")
def doc() -> str:
    """Show a list of libraries, along with the nav panel on the left"""
    kwdb = current_app.config['kwdb']

    libraries = get_collections(kwdb, libtype="library")
    resource_files = get_collections(kwdb, libtype="resource")
    hierarchy = get_navpanel_data(kwdb)

    return flask.render_template(
        "home.html",
        data={
            "libraries": libraries,
            "version": __version__,
            "libdoc": None,
            "hierarchy": hierarchy,
            "resource_files": resource_files,
        },
    )


@blueprint.route("/index")
def index():
    """Renders the homepage with a tree view of collections."""
    kwdb = current_app.config["kwdb"]
    libraries = get_collections(kwdb, libtype="library")
    resource_files = get_collections(kwdb, libtype="resource")

    return flask.render_template("libraryNames.html",
                                data={"libraries": libraries,
                                    "version": __version__,
                                    "resource_files": resource_files
                                })




@blueprint.route("/search/")
def search():
    """Show all keywords that match a pattern"""
    pattern = flask.request.args.get("pattern", "*").strip().lower()

    # if the pattern contains "in:<collection>" (eg: in:builtin),
    # filter results to only that (or those) collections
    # This was kind-of hacked together, but seems to work well enough
    collections = [c["name"].lower() for c in current_app.config['kwdb'].get_collections()]
    words = []
    filters = []
    if pattern.startswith("name:"):
        pattern = pattern[5:].strip()
        mode = "name"
    else:
        mode = "both"

    for word in pattern.split(" "):
        if word.lower().startswith("in:"):
            filters.extend([name for name in collections if name.startswith(word[3:])])
        else:
            words.append(word)
    pattern = " ".join(words)

    keywords = []
    for keyword in current_app.config['kwdb'].search(pattern, mode):
        kw = list(keyword)
        collection_id = kw[0]
        collection_name = kw[1].lower()
        if len(filters) == 0 or collection_name in filters:
            url = flask.url_for(".doc_for_library", collection_id=kw[0], keyword=kw[2])
            row_id = "row-%s.%s" % (
                keyword[1].lower(),
                keyword[2].lower().replace(" ", "-"),
            )
            keywords.append(
                {
                    "collection_id": keyword[0],
                    "collection_name": keyword[1],
                    "name": keyword[2],
                    "synopsis": keyword[3],
                    "version": __version__,
                    "url": url,
                    "row_id": row_id,
                }
            )

    keywords.sort(key=lambda kw: kw["name"])
    return flask.render_template(
        "search.html",
        data={"keywords": keywords, "version": __version__, "pattern": pattern},
    )


@blueprint.route("/keywords/<collection_id>/<keyword>", strict_slashes=False)
@blueprint.route("/keywords/<collection_id>", strict_slashes=False)
# def doc_for_library(collection_id, keyword=""):
def doc_for_library(collection_id, keyword=None) -> str:
    """Render library documentation"""
    kwdb = current_app.config["kwdb"]

    libdoc = kwdb.get_collection(collection_id)
    lib_doc_format = libdoc.get("doc_format", "ROBOT")

    keywords = []
    for (keyword_id, name, args, doc) in kwdb.get_keyword_data(collection_id):
        # args is a json list; convert it to actual list, and
        # then convert that to a string
        args = ", ".join(json.loads(args))
        doc_html = doc_to_html(doc, lib_doc_format)
        target = name == keyword
        keywords.append((name, args, doc_html, target))

    libdoc["doc"] = doc_to_html(libdoc["doc"], lib_doc_format)

    # this data is necessary for the nav panel
    hierarchy = get_navpanel_data(kwdb)

    return flask.render_template("library.html",
                                data={
                                        "keywords": keywords,
                                        "version": __version__,
                                        "libdoc": libdoc,
                                        "hierarchy": hierarchy,
                                        "collection_id": collection_id
                                    })

def get_collections(kwdb, libtype="*"):
    """Get list of collections from kwdb, then add urls necessary for hyperlinks"""
    collections = kwdb.get_collections(libtype=libtype)
    for result in collections:
        url = flask.url_for(".doc_for_library", collection_id=result["collection_id"])
        result["url"] = url

    return collections


def get_navpanel_data(kwdb):
    """Get navpanel data from kwdb, and add urls necessary for hyperlinks"""
    data = kwdb.get_keyword_hierarchy()
    for library in data:
        library["url"] = flask.url_for(
            ".doc_for_library", collection_id=library["collection_id"]
        )
        for keyword in library["keywords"]:
            url = flask.url_for(
                ".doc_for_library",
                collection_id=library["collection_id"],
                keyword=keyword["name"],
            )
            keyword["url"] = url

    return data



def doc_to_html(doc: str | None, doc_format: str = "ROBOT") -> str:
    """Convert a single Robot Framework documentation string to HTML.

    WHY:
        `LibdocHtmlWriter` writes a full interactive Libdoc HTML page and
        requires a *libdoc model* with a `.to_json()` method. Here we only have a
        plain docstring (``doc``), so we must use `DocToHtml`, which converts
        a single docstring from its source format (robot/html/text/rest) to HTML.

    Notes:
        - RF ≥ 4.0 moved `DocToHtml` to `robot.libdocpkg.htmlutils`.
        - Valid formats are ``ROBOT``, ``HTML``, ``TEXT``, ``REST`` (case-insensitive).
            An invalid value raises a `DataError` from Robot Framework.

    Returns:
        HTML string suitable for direct embedding in Jinja (mark as safe).
    """
    if not doc:
        return ""

    # Normalize the format to what RF expects (uppercase tokens).
    fmt = (doc_format or "ROBOT").upper()
    # DocToHtml is callable and returns the converted HTML.
    html = DocToHtml(fmt)(doc)  # see RF source for signature/behavior
    # If you want to prevent Jinja from escaping later, return Markup(html).
    # If template uses `|safe`, returning plain str is fine.
    return html

