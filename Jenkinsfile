pipeline {
    agent any

    environment {
        DOCKER_USER = 'shaffat01'
        IMAGE_NAME  = 'network-dashboard'
        IMAGE_TAG   = "${env.BUILD_NUMBER}"
        FULL_IMAGE  = "${DOCKER_USER}/${IMAGE_NAME}"
        ANSIBLE_DIR = '/home/jenkins/ansible-master'
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

        stage('Deploy via Ansible') {
            steps {
                echo "🚀 Running Ansible Deploy from ${ANSIBLE_DIR}"
                sh """
                    cd ${ANSIBLE_DIR}
                    ansible-playbook deploy.yml \
                      --vault-password-file .vault_pass \
                      -e "docker_image=${FULL_IMAGE}:${IMAGE_TAG}" \
                      -e "app_name=${IMAGE_NAME}"
                """
            }
        }

        stage('Health Check') {
            steps {
                echo "🔍 Checking App Health status..."
                sh """
                    for i in {1..12}; do
                        echo "Attempt \$i: Testing http://localhost:5001/health..."
                        if curl -sf http://localhost:5001/health; then
                            echo "\n✅ Health check passed!"
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
        }
        success {
            echo "✅ Network Dashboard LIVE: http://localhost:5001"
        }
        failure {
            echo "❌ Deployment Failed! Checking Docker logs..."
            sh 'docker logs network_dashboard || true'
        }
    }
}