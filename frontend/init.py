from webapp.core import app

if __name__ == '__main__':
    app.run(
        host=app.config['WEBAPP_HOST'],
        port=app.config['WEBAPP_PORT'],
        use_reloader=False
    )
