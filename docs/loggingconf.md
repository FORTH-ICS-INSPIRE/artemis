Logging can be configured by editing the following files:
```
local_configs/frontend/logging.yaml
local_configs/backend/logging.yaml
local_configs/monitor/logging.yaml
```
Logs (which are useful for debugging) can be accessed as follows:
```
docker-compose logs
```
The "-f" flag will provide you live logs while the tool is running.
If you need the logs from a particular running container, e.g., the backend, you can also do the following:
```
docker-compose exec backend bash
cd /var/log/artemis
```
Both containers use [Python's logging library](https://docs.python.org/3/library/logging.html) and can be configured as such. The tool supports SMTP, SMPTS and SYSLOG handlers for the loggers, which can be defined as follows:
```
smtps_handler:
    # artemis_utils.logging.TLSSMTPHandler for TLS
    # artemis_utils.logging.SSLSMTPHandler for SSL
    class: artemis_utils.logging.SSLSMTPHandler
    level: INFO
    formatter: simple
    mailhost:
    - smtp.server.com
    - port
    fromaddr: from@email.com
    toaddrs:
    - to1@email.com
    - to2@email.com
    subject: subject
    credentials:
    - username
    - password
    secure: True
```
Additionaly, we support Slack logging which can be defined as follows (you can generate the api token at https://api.slack.com/custom-integrations/legacy-tokens):
```
slack_handler:
    class: slacker_log_handler.SlackerLogHandler
    api_key: SLACK_API_TOKEN
    channel: "#general"
    username: "Hijack Announcer"
    level: INFO

... (then to add it to a logger)

    hijack_logger:
        level: INFO
        handlers: [slack_handler]
        propagate: no
```
Then, you can attach them to the already defined loggers based on their purpose. For example, backend loggers include:

* artemis_logger: Output of all (backend) services.
* mail_logger: Triggered on new hijack events (targeted information to avoid spamming for mail services - **only** triggered on hijack events). For its current use, check [this line](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/backend-services/detection/core/detection.py#L1043).
* hijack_logger: Triggered for every hijack update (not only on first trigger). Be careful to avoid being overwhelmed with messages in case you attach a handler to it! Useful for monitoring the progress of a hijack in terms of incoming BGP updates.
* taps_logger: Logger for the monitoring services.

*Note that you should attach a logger you would like to use.
For example, after you configure the `smtps` log handler in lines 32-50
within `local_configs/backend/logging.yaml` and optionally adding your custom
formatter after line 5, you should add the `smtps_handler` to the `mail_logger` handlers.*

In general, the logging.yaml files, besides auxiliary information, contain 3 sections that you can adjust according to your logging needs:

* **formatters**, which define *the format* of a log message and are used in handlers
* **handlers**, which define *how* a log message should be handled (e.g., at which level of criticality)
* **loggers**, which define *which handlers* should be used and at *which level* of criticality

For a useful tutorial on logging using yaml configurations and how to use them in Python, we refer the user to [this tutorial](https://fangpenlin.com/posts/2012/08/26/good-logging-practice-in-python/).

For further log customization, please check the following env variables [here](https://bgpartemis.readthedocs.io/en/latest/envvars/):
```
HIJACK_LOG_FILTER # for logging hijacks only with a certain community payload
HIJACK_LOG_FIELDS # for selecting which hijack fields to show in the logs
```
