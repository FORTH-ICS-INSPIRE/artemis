## Installation Steps (Linux)

We deployed successfully artemis on a microk8s instance in Ubuntu 18 LTS. To install it yourself you can follow this steps:

### 1. Download and install microk8s and helm
```
snap install microk8s --classic
snap install helm --classic
```

### 2. Start microk8s
```
microk8s.start
```

### 3. Enable the kubernetes dashboard, storage, dns
```
microk8s.enable dashboard storage dns
```

### 4. Install artemis helm-chart by running (**IMPORTANT**: add your values like other/example-values.yaml)
Initialize:
```
helm init
```
Add the artemis helm repo:
```
helm repo add artemis https://forth-ics-inspire.github.io/artemis
```
Check that the repo is present:
```
helm search -r 'artemis/*'
```
Check that the response is sth like this (the chart name is important):
```
artemis/artemis-chart   x.y.z       latest      ARTEMIS helm chart for deploying on kubernetes.
```
Finally to install the artemis helm chart there are two ways. If you want to use the online repository of artemis, then [download the configuration file](https://raw.githubusercontent.com/FORTH-ICS-INSPIRE/artemis/master/artemis-chart/values.yaml) and the [secrets configuration file](https://raw.githubusercontent.com/FORTH-ICS-INSPIRE/artemis/master/other/example-values.yaml) and start helm pointing to it (please change the secrets):
```
helm install -f values.yaml -f example-values.yaml artemis/artemis-chart
```
Or you can also point helm to your local artemis-chart folder if you cloned the repository (e.g., if you are testing an in-branch release):
```
helm install -f values.yaml -f example-values.yaml <path_to_artemis-chart>
```
You can delete releases on demand, by doing:
```
# find the release you want
helm list
helm delete <release_name> --purge
```
### 5. Login to kubernetes dashboard at
```
http://127.0.0.1:8080/api/v1/namespaces/kube-system/services/https:kubernetes-dashboard:/proxy
```
with token from
```
microk8s.kubectl -n kube-system describe secret $(microk8s.kubectl -n kube-system get secret | awk '/^kubernetes-dashboard-token-/{print $1}') | awk '$1=="token:"{print $2}'
```
### 6. Find nginx cluster IP from
```
http://127.0.0.1:8080/api/v1/namespaces/kube-system/services/https:kubernetes-dashboard:/proxy/#!/service?namespace=default
```
### 7. Visit artemis at the cluster IP with https

In case you want to use the CLI instead of the GUI:
```
microk8s.kubectl get pods -o wide
```
to get details of all pods (including their IP addresses).

Then proxy the nginx service to your localhost:
```
sudo microk8s.kubectl port-forward service/nginx 443:443
```

You can now access ARTEMIS on your localhost via HTTPS. If you want to make it available to an external interface you can use:
```
sudo microk8s.kubectl port-forward --address x.x.x.x service/nginx 443:443
```

## Using Ingress Controller (Enabled by default)

Ingress Controller is enabled by default in values.yaml file. You can disable the ingress controller in order to use the NGINX deployment approach instead. We already provide an [Ingress example](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/artemis-chart/templates/ingresses.yaml) that works with [NGINX Ingress Controller](https://github.com/kubernetes/ingress-nginx), an Ingress Controller maintained by the kubernetes community. You can run this controller from within microk8s by running `microk8s.enable ingress`.

By default, the hostname defaults to `artemis.dev`; to change it, you can provide a value in your yaml file when installing with helm for value `ingress.host`:
```
echo 'ingress.host: artemis.dev' >> other/example-values.yaml
helm install -f other/example-values artemis/artemis-chart
```

If you don't have a DNS record you can change your `/etc/hosts` file to point to the clusters external IP for the specified hostname:
```
echo 'x.x.x.x artemis.dev' >> /etc/hosts
```

## Customization of Kubernetes Deployment

When you install ARTEMIS's helm chart you need to provide some values in a .yalm file (for example see `other/example-values.yaml`):

```
hasuraSecret   # Alphanumeric string that is used as the super-secret of hasura
jwtSecret      # Secret used for the JWT authentication
privKey        # Private key for the HTTPS certificate
certificate    # HTTPS certificate
### OPTIONAL ###
hostName       # Host name for Ingress Controller
```
In the docker-compose approach we have a `.env` file that you can change the default behaviour of the application. Other than the secrets above you can define other values as well. The structure of the file needs to be similar as the one located in `artemis-chart/values.yaml`. The values have different naming method but the functionality is similar as the ones defined in the environment variables guide.

Then you can install ARTEMIS's helm chart with your custom values with:
```
helm install -f values.yaml -f example-values.yaml artemis/artemis-chart
```

## Known issues
* http instead of https redirection: please check [this issue](https://github.com/FORTH-ICS-INSPIRE/artemis/issues/200)
