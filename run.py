from webapp import app

if __name__ == '__main__':
    if 'WEBAPP_KEY' in app.config and 'WEBAPP_CRT' in app.config:
        print('SSL: enabled')
        # http://flask.pocoo.org/snippets/111/
        # https://www.digitalocean.com/community/tutorials/openssl-essentials-working-with-ssl-certificates-private-keys-and-csrs
        context = (app.config['WEBAPP_CRT'], app.config['WEBAPP_KEY'])
        app.run(
            host=app.config['WEBAPP_HOST'],
            port=app.config['WEBAPP_PORT'],
            ssl_context=context
        )
    else:
        print('SSL: disabled')
        app.run(
            host=app.config['WEBAPP_HOST'],
            port=app.config['WEBAPP_PORT']
        )
