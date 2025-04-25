# AWS ECS 배포 가이드

이 문서는 NDNS 서비스를 AWS ECS (Elastic Container Service)에 배포하는 방법을 설명합니다.

## 사전 준비 사항

1. [AWS CLI](https://aws.amazon.com/cli/) 설치 및 설정
2. [Docker](https://www.docker.com/get-started) 설치
3. [AWS ECR](https://aws.amazon.com/ecr/) (Elastic Container Registry) 접근 권한

## 1. 도커 이미지 빌드 및 테스트

먼저 로컬에서 도커 이미지를 빌드하고 테스트합니다:

```bash
# 도커 이미지 빌드
docker build -t ndns:latest .

# 로컬에서 테스트 실행
docker run -p 8000:8000 \
  -e NAVER_CLIENT_ID=your_client_id \
  -e NAVER_CLIENT_SECRET=your_client_secret \
  ndns:latest
```

브라우저에서 `http://localhost:8000/docs`에 접속하여 API 문서를 확인합니다.

## 2. AWS ECR에 이미지 푸시

```bash
# AWS 계정 ID 변수 설정
export AWS_ACCOUNT_ID=323502797000

# AWS 로그인
aws ecr get-login-password --profile ndns --region ap-northeast-2 | docker login --username AWS --password-stdin ${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com

# ECR 리포지토리 생성 (한 번만 실행)
aws ecr create-repository --profile ndns --repository-name ndns --region ap-northeast-2

# 이미지 태그 지정
docker tag ndns:latest ${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/ndns:latest

# ECR에 이미지 푸시
docker push ${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/ndns:latest
```

## 3. ECS Fargate 설정

### 3.1 작업 정의 (Task Definition) 생성

AWS 콘솔에서 다음 단계를 수행하거나 아래 CLI 명령을 사용할 수 있습니다:

```bash
# 작업 정의 JSON 파일 생성
cat > ndns-task-definition.json << EOF
{
  "family": "ndns-task",
  "executionRoleArn": "arn:aws:iam::${AWS_ACCOUNT_ID}:role/ecsTaskExecutionRole",
  "networkMode": "awsvpc",
  "containerDefinitions": [
    {
      "name": "ndns",
      "image": "${AWS_ACCOUNT_ID}.dkr.ecr.ap-northeast-2.amazonaws.com/ndns:latest",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "hostPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "NAVER_CLIENT_ID", "value": "your_client_id"},
        {"name": "NAVER_CLIENT_SECRET", "value": "your_client_secret"},
        {"name": "TESSDATA_PREFIX", "value": "/usr/share/tesseract-ocr/4.00/tessdata/"}
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/ndns",
          "awslogs-region": "ap-northeast-2",
          "awslogs-stream-prefix": "ndns"
        }
      }
    }
  ],
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048"
}
EOF

# 작업 정의 등록
aws ecs register-task-definition --profile ndns --cli-input-json file://ndns-task-definition.json --region ap-northeast-2
```

### 3.2 클러스터 생성

```bash
# 클러스터 생성
aws ecs create-cluster --profile ndns --cluster-name ndns-cluster --region ap-northeast-2
```

### 3.3 서비스 생성

```bash
# 서브넷 및 보안 그룹 ID 확인 (VPC ID는 실제 환경에 맞게 수정 필요)
export VPC_ID=$(aws ec2 describe-vpcs --profile ndns --query "Vpcs[0].VpcId" --output text --region ap-northeast-2)
export SUBNET_IDS=$(aws ec2 describe-subnets --profile ndns --filters "Name=vpc-id,Values=${VPC_ID}" --query "Subnets[*].SubnetId" --output text --region ap-northeast-2 | tr '\t' ',')

# 보안 그룹 생성 (이미 존재하는 경우 기존 ID 사용)
export SECURITY_GROUP_ID=$(aws ec2 create-security-group --profile ndns --group-name ndns-sg --description "Security group for NDNS" --vpc-id ${VPC_ID} --region ap-northeast-2 --output text)

# 포트 8000 인바운드 규칙 추가
aws ec2 authorize-security-group-ingress --profile ndns --group-id ${SECURITY_GROUP_ID} --protocol tcp --port 8000 --cidr 0.0.0.0/0 --region ap-northeast-2

# 서비스 생성
aws ecs create-service --profile ndns \
  --cluster ndns-cluster \
  --service-name ndns-service \
  --task-definition ndns-task \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$(echo $SUBNET_IDS | tr ',' ' ')],securityGroups=[${SECURITY_GROUP_ID}],assignPublicIp=ENABLED}" \
  --region ap-northeast-2
```

## 4. 영구 스토리지 설정 (선택 사항)

캐시 데이터 영구 저장을 위해 EFS(Elastic File System)를 사용할 수 있습니다:

```bash
# EFS 생성
aws efs create-file-system --profile ndns --region ap-northeast-2 --performance-mode generalPurpose --throughput-mode bursting

# EFS ID 기록 (출력 확인)
# export EFS_ID=fs-xxxxxxxx
```

이후 작업 정의에 EFS 볼륨을 추가합니다.

## 5. CloudWatch 로그 모니터링

로그 그룹이 없으면 생성합니다:

```bash
aws logs create-log-group --profile ndns --log-group-name /ecs/ndns --region ap-northeast-2
```

## 6. 배포 후 확인

```bash
# 서비스 상태 확인
aws ecs describe-services --profile ndns --cluster ndns-cluster --services ndns-service --region ap-northeast-2

# 작업 목록 확인
aws ecs list-tasks --profile ndns --cluster ndns-cluster --service-name ndns-service --region ap-northeast-2

# 공개 IP 주소 확인
export TASK_ARN=$(aws ecs list-tasks --profile ndns --cluster ndns-cluster --service-name ndns-service --query taskArns[0] --output text --region ap-northeast-2)
export ENI_ID=$(aws ecs describe-tasks --profile ndns --cluster ndns-cluster --tasks ${TASK_ARN} --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' --output text --region ap-northeast-2)
aws ec2 describe-network-interfaces --profile ndns --network-interface-ids ${ENI_ID} --query 'NetworkInterfaces[0].Association.PublicIp' --output text --region ap-northeast-2
```

서비스에 접근: `http://<PUBLIC_IP>:8000`

## 7. 자동화된 배포 (CI/CD)

GitHub Actions 또는 AWS CodePipeline을 사용하여 배포 자동화 구성을 추가할 수 있습니다. 이는 선택 사항입니다.

## 문제 해결

- **컨테이너 시작 실패**: CloudWatch 로그 확인
- **API 접근 불가**: 보안 그룹 및 네트워크 설정 확인
- **메모리 부족**: 작업 정의의 메모리 할당량 증가

## 참고자료

- [AWS Fargate 사용 설명서](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/AWS_Fargate.html)
- [Amazon ECS 컨테이너 정의](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html)
- [Amazon ECR 사용 설명서](https://docs.aws.amazon.com/AmazonECR/latest/userguide/what-is-ecr.html)
