# kubernetes-fan-control

A small web app for controlling a ceiling fan (speed + light) over UDP
broadcast, meant to run as a single pod in a Kubernetes cluster.

## How it works

The fan receiver listens for JSON messages broadcast to
`192.168.50.255:12345`. The app is a Flask backend with a one-page UI
(High / Medium / Low / Off + a light toggle button); each button click
triggers a POST to the backend, which sends the matching UDP broadcast:

| Button | UDP payload |
|---|---|
| High | `{"high":"on"}` |
| Medium | `{"medium":"on"}` |
| Low | `{"low":"on"}` |
| Off | `{"off":"off"}` |
| Light toggle | `{"lights":"toggle"}` |

The fan is one-way (no status feedback), so the UI just confirms a command
was sent — it can't show the fan's actual current state.

## Important: networking

`192.168.50.255` is a broadcast address on your physical LAN. Regular pod
networking (the CNI overlay) generally can't reach it — broadcasts don't
cross the overlay/NAT boundary. Because of that, `deployment.yaml` sets
`hostNetwork: true`, so the pod sends the broadcast from the node's own
network interface. Make sure whichever node the pod lands on is actually
attached to `192.168.50.0/24` (use the commented-out `nodeSelector` in the
deployment if your cluster spans multiple network segments).

## Local development

```bash
cd app
pip install -r requirements.txt
python app.py
# open http://localhost:8080
```

## Build & deploy

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t kregistry.siwko.org:5000/fan-control:latest --push .

kubectl apply -f deployment.yaml
kubectl apply -f external-dns-linode.yaml
```

Then browse to `http://fan.siwko.org:8080`, or `http://<node-ip>:8080`
directly since the pod is on the host network.

`Jenkinsfile` automates all of the above (multi-arch build, `kubectl apply` +
`set image`, external-dns reconcile, rollout check, and pruning old registry
tags), same pattern as `kubernetes-openliberty` / `kubernetes-test-one`. It
runs on the `docker-builder` Jenkins agent, which already has buildx and
cluster access configured — no credentials to fill in.

## DNS (fan.siwko.org)

The `fan-control` Service is `type: LoadBalancer` with the annotation
`external-dns.alpha.kubernetes.io/hostname: fan.siwko.org`. On this cluster,
MetalLB (see `kubernetes-test-one/metal-lb-config.yml`) hands the Service a
VIP from its pool, and the `external-dns` controller
(`external-dns-linode.yaml`) watches for that annotation and publishes the
VIP as an A record for `fan.siwko.org` in the `siwko.org` Linode zone.

`external-dns-linode.yaml` deploys the shared, cluster-wide external-dns
controller — it's the same controller already running for the other
projects on this cluster (same namespace/names), so re-applying it here just
reconciles the existing Deployment rather than creating a second one. It
does assume the `linode-api-token` Secret already exists in the
`external-dns` namespace; if it doesn't yet, create it once:

```bash
kubectl create namespace external-dns
kubectl create secret generic linode-api-token \
  --from-literal=token=<your-linode-api-token> \
  -n external-dns
```
