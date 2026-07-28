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
```

Then browse to `http://<node-ip>:30090` (NodePort) or `http://<node-ip>:8080`
directly, since the pod is on the host network.

`Jenkinsfile` automates the build/push/deploy above (multi-arch build,
`kubectl apply` + `set image`, rollout check, and pruning old registry tags),
same pattern as `kubernetes-openliberty`. It runs on the `docker-builder`
Jenkins agent, which already has buildx and cluster access configured — no
credentials to fill in.
