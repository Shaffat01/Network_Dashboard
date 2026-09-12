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
                      python -c "import app; import database; print('✅ All Core Modules Imported Successfully!')"
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
                    # DOCKER_IMAGE এনভায়রনমেন্ট সেট করা
                    export DOCKER_IMAGE=${FULL_IMAGE}:${IMAGE_TAG}
                    
                    # docker compose (স্পেস সহ) ব্যবহার করুন
                    docker compose down || true
                    docker compose pull
                    docker compose up -d --remove-orphans
                """
            }
        }

        stage('Health Check') {
            steps {
                echo "🔍 Checking App Health status..."
                sh """
                    sleep 10
                    # Flask Health endpoint চেক
                    curl -sf http://localhost:5001/health
                    echo ""
                    # Main Page চেক
                    curl -sf http://localhost:5001/ | head -c 200
                    echo ""
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
            echo "✅ LIVE: http://YOUR_PRIVATE_IP:5001"
            echo "✅ Docker Hub: https://hub.docker.com/r/${DOCKER_USER}/${IMAGE_NAME}"
        }
        failure {
            echo "❌ Pipeline failed"
        }
    }
}