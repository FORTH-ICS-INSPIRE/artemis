You can configure Google SSO as an authentication method. You need to change the following variables in the `.env` file:

```
# Google SSO configuration
GOOGLE_ENABLED=false
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

```

Turn GOOGLE_ENABLED from false to true and create a Google app with OAuth 2.0 credentials, to get a Client ID and secret.
To do so, follow the official guide: https://support.google.com/cloud/answer/6158849.
