pipeline {
    agent any

    environment {
        DOCKER_USER = 'shaffat01'
        IMAGE_NAME  = 'network-dashboard'
        IMAGE_TAG   = "${env.BUILD_NUMBER}"
        FULL_IMAGE  = "${DOCKER_USER}/${IMAGE_NAME}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
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
                      python -c "import app; import database; print('✅ Core Modules OK')"
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

        stage('Deploy with Docker Compose') {
            steps {
                echo "🚀 Deploying multi-container setup (Flask + MySQL) on port 5001"
                sh """
                    export DOCKER_IMAGE=${FULL_IMAGE}:${IMAGE_TAG}
                    docker compose down --volumes --remove-orphans || true
                    docker compose up -d
                """
            }
        }

        stage('Health Check') {
            steps {
                echo "🔍 Checking App Health status with retry logic..."
                sh """
                    for i in {1..12}; do
                        echo "Attempt \$i: Testing http://localhost:5001/health..."
                        if curl -sf http://localhost:5001/health; then
                            echo "\n✅ Health check passed!"
                            exit 0
                        fi
                        echo "App/DB is initializing... Waiting 5 seconds..."
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
            echo "✅ LIVE: http://YOUR_SERVER_IP:5001"
            echo "✅ Docker Hub: https://hub.docker.com/r/${DOCKER_USER}/${IMAGE_NAME}"
        }
        failure {
            echo "❌ Pipeline failed! Fetching logs..."
            # ফেইল করলে কন্টেইনারের লোগ প্রিন্ট করে দেখাবে সমস্যা কোথায়
            sh 'docker compose logs --tail=50 || true'
        }
    }
}