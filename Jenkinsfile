pipeline {
    agent { label 'docker-builder' }

    environment {
        // Use the domain name your K8s cluster uses to resolve the registry
        REGISTRY_DOMAIN = 'kregistry.siwko.org:5000'
        IMAGE_NAME      = 'fan-control'
        IMAGE_TAG       = "${env.BUILD_NUMBER}"
        DEPLOYMENT_NAME = 'fan-control'
        // How many recent numbered build tags to keep in the registry when pruning
        RETAIN_COUNT    = '10'
    }

    stages {
        stage('Checkout Code') {
            steps {
                // Jenkins automatically pulls the code from Git here
                checkout scm
            }
        }

        stage('Build & Push Multi-Arch Image') {
            steps {
                echo "Building & pushing multi-arch image: ${REGISTRY_DOMAIN}/${IMAGE_NAME}:${IMAGE_TAG}..."
                // Cluster has both amd64 (RHEL) and arm64 (Orange Pi) nodes, so the image
                // manifest must cover both platforms. Multi-platform images can't be
                // docker-loaded locally, so build and push happen in one buildx step.
                // Reuse the builder across runs (preserves BuildKit's layer cache and avoids
                // tearing down a builder another concurrent job may be using); only create
                // it if missing. The docker-container driver runs BuildKit in its own
                // container, isolated from the host daemon.json insecure-registries setting,
                // so it needs its own config -- baked in once via a fixed host path, not the
                // repo, so any project's Jenkinsfile can reuse the same line.
                sh "docker buildx inspect multiarch-builder >/dev/null 2>&1 || docker buildx create --name multiarch-builder --driver docker-container --config /etc/buildkit/buildkitd.toml --bootstrap"
                sh "docker buildx use multiarch-builder"
                sh """
                    docker buildx build \
                      --platform linux/amd64,linux/arm64 \
                      -t ${REGISTRY_DOMAIN}/${IMAGE_NAME}:${IMAGE_TAG} \
                      -t ${REGISTRY_DOMAIN}/${IMAGE_NAME}:latest \
                      --push .
                """
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                echo "Applying manifests and updating deployment image..."
                // Always apply the manifests first so Service changes take effect
                sh "kubectl apply -f k8s/deployment.yaml"
                // Then update the image to the exact build tag
                sh "kubectl set image deployment/${DEPLOYMENT_NAME} fan-control=${REGISTRY_DOMAIN}/${IMAGE_NAME}:${IMAGE_TAG}"
            }
        }

        stage('Deploy External DNS to Kubernetes') {
            steps {
                echo "Applying external dns deployment"
                sh "kubectl apply -f k8s/external-dns-linode.yaml"
            }
        }

        stage('Verify Deployment Status') {
            steps {
                echo "Verifying rollout status..."
                // Actively monitor the rollout to ensure it doesn't get stuck (e.g. on an ImagePullBackOff)
                sh "kubectl rollout status deployment/${DEPLOYMENT_NAME} --timeout=2m"
            }
        }

        stage('Prune Old Registry Tags') {
            steps {
                echo "Pruning ${IMAGE_NAME} tags in ${REGISTRY_DOMAIN}, keeping the ${RETAIN_COUNT} most recent numbered builds..."
                // Deletes old manifests via the registry HTTP API so the registry stops
                // serving them. This does NOT reclaim disk space -- the underlying blobs
                // stay on disk until `registry garbage-collect` runs (see
                // scripts/registry-gc.sh in kubernetes-openliberty), so this is safe to run
                // after every build. "latest" and any non-numeric tag are never touched.
                // Requires jq on the agent.
                sh '''
                    set -e
                    TAGS_JSON=$(curl -sf "https://${REGISTRY_DOMAIN}/v2/${IMAGE_NAME}/tags/list")
                    OLD_TAGS=$(echo "$TAGS_JSON" | jq -r '.tags[]?' | grep -E '^[0-9]+$' | sort -rn | tail -n +$((RETAIN_COUNT + 1)))

                    if [ -z "$OLD_TAGS" ]; then
                        echo "Nothing to prune."
                    fi

                    for TAG in $OLD_TAGS; do
                        DIGEST=$(curl -sI \
                            -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json" \
                            -H "Accept: application/vnd.oci.image.index.v1+json" \
                            "https://${REGISTRY_DOMAIN}/v2/${IMAGE_NAME}/manifests/${TAG}" \
                            | grep -i '^docker-content-digest:' | tr -d '\\r' | awk '{print $2}')

                        if [ -n "$DIGEST" ]; then
                            echo "Deleting ${IMAGE_NAME}:${TAG} (${DIGEST})"
                            curl -sf -X DELETE "https://${REGISTRY_DOMAIN}/v2/${IMAGE_NAME}/manifests/${DIGEST}" || echo "Delete failed for ${TAG}, continuing"
                        else
                            echo "Could not resolve digest for tag ${TAG}, skipping"
                        fi
                    done
                '''
            }
        }
    }

    post {
        always {
            echo "Cleaning up local build workspace..."
            // Clean up old workspace files to prevent RHEL disk clutter
            cleanWs()
        }
        success {
            echo "Pipeline completed successfully! Build ${IMAGE_TAG} is now live."
        }
        failure {
            echo "Pipeline failed. Check build logs for details."
        }
    }
}
