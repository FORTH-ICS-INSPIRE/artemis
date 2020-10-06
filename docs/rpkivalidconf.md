## Basics
We employ [rtrlib](https://github.com/rtrlib/rtrlib) and its [Python binding](https://github.com/rtrlib/python-binding) as a client in order to speak the RTR protocol with a RTR server. You can use your own server or optionally setup [routinator](https://github.com/NLnetLabs/routinator) (as described in the following section) as another ARTEMIS microservice.

In any case, you will need to specify the following `.env` variables, if you want to see the status of hijacked prefixes as seen in RPKI:
```
RPKI_VALIDATOR_ENABLED=true # default: false
RPKI_VALIDATOR_HOST=<YOUR_RPKI_RTR_SERVER> # default: routinator, if you follow next section
RPKI_VALIDATOR_PORT=3323 # default RTR port
```
The explanation of the different possible RPKI characterizations you will see is:
```
"NA" → Non Applicable
"VD" → Valid
"IA" → Invalid ASN
"IL" → Invalid Prefix Length
"IU" → Invalid Unknown
"NF" → Not found
```

## Optional: setup ARTEMIS validator
*Note: this is needed only if you do not have a custom validator and RTR speaker that you would like to use.*

We comply to the instructions in [this repository](https://github.com/NLnetLabs/routinator). Please run:
```
mkdir -p local_configs/routinator/tals && \
sudo chown -R 1012:1012 local_configs/routinator/tals && \
mkdir -p local_configs/routinator/rpki-repo && \
sudo chown -R 1012:1012 local_configs/routinator/rpki-repo && \
cp other/routinator/routinator.conf local_configs/routinator/routinator.conf && \
sudo chown -R 1012:1012 local_configs/routinator/routinator.conf
```
```
sudo docker run --rm -v $(pwd)/local_configs/routinator/tals:/home/routinator/.rpki-cache/tals nlnetlabs/routinator init -f --accept-arin-rpa
```
```
docker-compose -f docker-compose.yaml ... -f docker-compose.routinator.yaml up -d
```

In your .env change the RPKI_VALIDATOR_ENABLED to true:
```
RPKI_VALIDATOR_ENABLED=true
```
Then reload your containers after the configuration change:
```
docker-compose -f docker-compose.yaml -f docker-compose.routinator.yaml up -d
```

You are all set!
