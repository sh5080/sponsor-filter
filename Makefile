.PHONY: setup run test lint clean venv

# 가상 환경 생성
venv:
	python3 -m venv .venv

# 기본 환경 설정
setup: venv
	. .venv/bin/activate && python -m pip install -r requirements.txt

# 개발 서버 실행
run:
	. .venv/bin/activate && uvicorn app.main:app --reload

# 프로덕션 서버 실행
run-prod:
	. .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000

# 테스트 실행
test:
	. .venv/bin/activate && pytest

# 코드 린트 검사
lint:
	. .venv/bin/activate && flake8 app tests

# 캐시 파일 정리
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".coverage" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name ".tox" -exec rm -rf {} +
	find . -type d -name "dist" -exec rm -rf {} +
	find . -type d -name "build" -exec rm -rf {} +

# 도움말
help:
	@echo "사용 가능한 명령어:"
	@echo "  make setup      - 필요한 패키지 설치"
	@echo "  make run        - 개발 서버 실행"
	@echo "  make run-prod   - 프로덕션 서버 실행"
	@echo "  make test       - 테스트 실행"
	@echo "  make lint       - 코드 린트 검사"
	@echo "  make clean      - 캐시 파일 정리" 