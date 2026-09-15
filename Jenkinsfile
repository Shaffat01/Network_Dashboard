pipeline {
    agent any

    environment {
        DOCKER_USER = 'shaffat01'
        IMAGE_NAME  = 'network-dashboard'
        IMAGE_TAG   = "${env.BUILD_NUMBER}"
        FULL_IMAGE  = "${DOCKER_USER}/${IMAGE_NAME}"
        // Ansible deploy target (change if needed)
        DEPLOY_HOST = '192.168.1.50'   // ← আপনার সার্ভার IP
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'ls -la'
            }
        }

        stage('Build Image') {
            steps {
                echo "🐳 Building ${FULL_IMAGE}:${IMAGE_TAG}"
                sh """
                    docker build -t ${FULL_IMAGE}:${IMAGE_TAG} .
                    docker tag ${FULL_IMAGE}:${IMAGE_TAG} ${FULL_IMAGE}:latest
                """
            }
        }

        stage('Test') {
            steps {
                echo "🧪 Running Basic Python Import Tests"
                sh """
                    docker run --rm ${FULL_IMAGE}:${IMAGE_TAG} \
                      python -c "import app; import database; import config; print('✅ Core Modules OK')"
                """
            }
        }

        stage('Push to Docker Hub') {
            steps {
                echo "📤 Login + Push to Docker Hub"
                withCredentials([usernamePassword(
                    credentialsId: 'docker-hub-credentials',
                    usernameVariable: 'DH_USER',
                    passwordVariable: 'DH_PASS'
                )]) {
                    sh """
                        echo "\$DH_PASS" | docker login -u "\$DH_USER" --password-stdin
                        docker push ${FULL_IMAGE}:${IMAGE_TAG}
                        docker push ${FULL_IMAGE}:latest
                    """
                }
            }
        }

        stage('Deploy with Ansible') {
            steps {
                echo "🚀 Ansible deploying ${FULL_IMAGE}:${IMAGE_TAG} to ${DEPLOY_HOST}"
                withCredentials([
                    usernamePassword(
                        credentialsId: 'docker-hub-credentials',
                        usernameVariable: 'DH_USER',
                        passwordVariable: 'DH_PASS'
                    ),
                    sshUserPrivateKey(
                        credentialsId: 'ansible-ssh-key',   // Jenkins-এ SSH key credential বানান
                        keyFileVariable: 'SSH_KEY',
                        usernameVariable: 'SSH_USER'
                    )
                ]) {
                    sh """
                        # Dynamic inventory
                        cat > /tmp/inventory.ini << EOF
[dashboard]
${DEPLOY_HOST} ansible_user=\${SSH_USER} ansible_ssh_private_key_file=\${SSH_KEY} ansible_ssh_common_args='-o StrictHostKeyChecking=no'
EOF

                        ansible-playbook \
                          -i /tmp/inventory.ini \
                          ansible/deploy.yml \
                          -e "docker_image=${FULL_IMAGE}:${IMAGE_TAG}" \
                          -e "docker_user=\${DH_USER}" \
                          -e "docker_pass=\${DH_PASS}" \
                          -e "app_port=5001"
                    """
                }
            }
        }

        stage('Health Check') {
            steps {
                echo "🔍 Checking App Health..."
                sh """
                    for i in {1..15}; do
                        echo "Attempt \$i: http://${DEPLOY_HOST}:5001/health"
                        if curl -sf http://${DEPLOY_HOST}:5001/health; then
                            echo ""
                            echo "✅ Health check PASSED!"
                            exit 0
                        fi
                        sleep 5
                    done
                    echo "❌ Health check timed out!"
                    exit 1
                """
            }
        }
    }

    post {
        always {
            sh 'docker logout || true'
            sh 'docker image prune -f || true'
            cleanWs()
        }
        success {
            echo "✅ LIVE  → http://${DEPLOY_HOST}:5001"
            echo "✅ Image → https://hub.docker.com/r/${DOCKER_USER}/${IMAGE_NAME}"
        }
        failure {
            echo "❌ Pipeline failed!"
        }
    }
}