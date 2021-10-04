## Installation Steps (Linux)

We deployed successfully artemis on a microk8s instance in Ubuntu 18 LTS. To install it yourself you can follow this steps:

### 1. Download and install microk8s (includes helm3 addon)

```
snap install microk8s --classic
```

### 2. Start microk8s

```
microk8s.start
```

Output:

```
$ microk8s.start
Started.
```

### 3. Enable the kubernetes dashboard, storage, dns

```
microk8s.enable dashboard storage dns helm3
```

Output:

```
microk8s.enable dashboard storage dns helm3
Enabling Kubernetes Dashboard

Addon metrics-server is already enabled.
Applying manifest
...
Addon storage is already enabled.
Addon dns is already enabled.
Addon helm3 is already enabled.
```

### 4. Install artemis helm-chart by running (**IMPORTANT**: add your values like other/example-values.yaml)

Add the artemis helm repo:

```
microk8s.helm3 repo add artemis https://forth-ics-inspire.github.io/artemis
```

Output:

```
microk8s.helm3 repo add artemis https://forth-ics-inspire.github.io/artemis
"artemis" has been added to your repositories
```

Check that the repo is present:

```
microk8s.helm3 search repo 'artemis'
```

Check that the response is sth like this (the chart name is important):

```
NAME                 	CHART VERSION	APP VERSION	DESCRIPTION
artemis/artemis-chart	x.y.z        	latest     	ARTEMIS helm chart for deploying on kubernetes.
```

Finally to install the artemis helm chart there are two ways. If you want to use the online repository of artemis, then [download the configuration file](https://raw.githubusercontent.com/FORTH-ICS-INSPIRE/artemis/master/artemis-chart/values.yaml) and the [secrets configuration file](https://raw.githubusercontent.com/FORTH-ICS-INSPIRE/artemis/master/other/example-values.yaml) and start helm pointing to it (please change the secrets):

```
microk8s.helm3 install -f values.yaml -f example-values.yaml artemis artemis/artemis-chart
```

Or you can also point helm to your local artemis-chart folder if you cloned the repository (e.g., if you are testing an in-branch release):

```
microk8s.helm3 install -f values.yaml -f example-values.yaml artemis <path_to_artemis-chart>
```

Output:

```
microk8s.helm3 install -f artemis-chart/values.yaml -f other/example-values.yaml artemis ./artemis-chart
walk.go:74: found symbolic link in path: /home/.../Projects/artemis/artemis-chart/files/configmaps/config.yaml resolves to /home/.../Projects/artemis/backend-services/configs/config.yaml
...
NAME: artemis
LAST DEPLOYED: Mon Apr 26 11:17:31 2021
NAMESPACE: default
STATUS: deployed
REVISION: 1
TEST SUITE: None
NOTES:
1. Get the application URL by running these commands:
  https://artemis.com/
```

You can delete releases on demand, by doing:

```
# find the release you want
microk8s.helm3 list
microk8s.helm3 uninstall <release>
```

### 5. Login to kubernetes dashboard

Setup proxy:

```
microk8s kubectl port-forward -n kube-system service/kubernetes-dashboard 10443:443
```

Then visit:

```
https://127.0.0.1:10443
```

with token from

```
microk8s.kubectl -n kube-system describe secret $(microk8s.kubectl -n kube-system get secret | awk '/^kubernetes-dashboard-token-/{print $1}') | awk '$1=="token:"{print $2}'
```

You can have a total overview of what is going on in your cluster on this dashboard.

## 6. Using Ingress Controller (Enabled by default)

Ingress Controller is enabled by default in values.yaml file. You can disable the ingress controller in order to use the NGINX deployment approach instead. We already provide an [Ingress example](https://github.com/FORTH-ICS-INSPIRE/artemis/blob/master/artemis-chart/templates/ingresses.yaml) that works with [NGINX Ingress Controller](https://github.com/kubernetes/ingress-nginx), an Ingress Controller maintained by the kubernetes community. You can run this controller from within microk8s by running `microk8s.enable ingress`.

By default, the hostname defaults to `artemis.com`; to change it, you can provide a value in your yaml file when installing with helm for value `ingress.host`:

```
echo 'ingress.host: artemis.com' >> other/example-values.yaml
microk8s.helm3 install -f other/example-values artemis artemis/artemis-chart
```

If you don't have a DNS record you can change your `/etc/hosts` file to point to the clusters external IP for the specified hostname:

```
echo 'x.x.x.x artemis.com' >> /etc/hosts
```

## Customization of Kubernetes Deployment

When you install ARTEMIS's helm chart you need to provide some values in a .yalm file (for example see `other/example-values.yaml`):

```
hasuraSecret   # Alphanumeric string that is used as the super-secret of hasura
jwtSecret      # Secret used for the JWT authentication
csrfSecret     # Secret used for CSRF protection
privKey        # Private key for the HTTPS certificate
certificate    # HTTPS certificate
apiKey         # secret used for frontend API use
captchaSecret  # secret used for Captcha protection
### OPTIONAL ###
hostName       # Host name for Ingress Controller
```

In the docker-compose approach we have a `.env` file that you can change the default behaviour of the application. Other than the secrets above you can define other values as well. The structure of the file needs to be similar as the one located in `artemis-chart/values.yaml`. The values have different naming methods but the functionality is similar as the ones defined in the environment variables guide.

Then you can install ARTEMIS's helm chart with your custom values with:

```
microk8s.helm3 install -f values.yaml -f example-values.yaml artemis artemis/artemis-chart
```

## Known issues

- http instead of https redirection: please check [this issue](https://github.com/FORTH-ICS-INSPIRE/artemis/issues/200)
