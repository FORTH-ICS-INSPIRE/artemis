# Auth

We offer a REST API for user authentication and authorization, served by the frontend container.
Please check the official documentation:

- [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docs/api-documentation.pdf) (pdf)
- [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docs/swagger.yaml) (yaml), or
- [here](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/docs/api-documentation.html) (html-download locally before displaying!).

The basic process (e.g., to get an access token via CLI) is as follows:

1. login (`api/auth/login/<credentials|ldap>`)
2. get `JWT` token (`api/auth/jwt/`)

Please check the documentation for more endpoints and features.
