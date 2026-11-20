// Same pipeline as .github/workflows/ci.yml, for a Jenkins agent with Docker.
pipeline {
  agent any
  environment {
    IMAGE = "sensor-api:${env.GIT_COMMIT?.take(7) ?: 'local'}"
  }
  options { timestamps(); timeout(time: 20, unit: 'MINUTES') }
  stages {
    stage('Lint & test') {
      agent { docker { image 'python:3.12-slim'; reuseNode true } }
      steps {
        sh 'pip install -q -r requirements-dev.txt'
        sh 'ruff check .'
        sh 'pytest -q --junitxml=results/junit.xml'
      }
      post { always { junit 'results/junit.xml' } }
    }
    stage('Build image') {
      steps { sh "docker build --build-arg APP_VERSION=${env.GIT_COMMIT?.take(7)} -t ${IMAGE} ." }
    }
    stage('Smoke test') {
      steps {
        sh """
          docker rm -f api-smoke || true
          docker run -d --name api-smoke -p 18000:8000 ${IMAGE}
          for i in \$(seq 1 20); do curl -fs localhost:18000/healthz && break; sleep 1; done
          curl -fs -X POST localhost:18000/readings -H 'content-type: application/json' -d '{"machine_id":"ci-1","value":42}'
        """
      }
      post { always { sh 'docker rm -f api-smoke || true' } }
    }
    stage('Deploy to minikube') {
      when { branch 'main' }
      steps {
        sh "minikube image load ${IMAGE}"
        sh 'kubectl apply -k k8s/'
        sh "kubectl set image deployment/sensor-api sensor-api=${IMAGE}"
        sh 'kubectl rollout status deployment/sensor-api --timeout=120s'
      }
    }
  }
}
