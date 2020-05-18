# from webapp.core import app
from flask import Blueprint
from flask import render_template


errors = Blueprint("errors", __name__, template_folder="templates")


@errors.route("/400", methods=["GET"])
def error400():
    return render_template("/errors/400.htm"), 400


@errors.route("/500", methods=["GET"])
def error500():
    return render_template("/errors/500.htm"), 500
