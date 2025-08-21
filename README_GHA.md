# Naver Shopping Connect Lite — GitHub Actions 빌드
로컬에 Python 설치 없이, GitHub Actions(클라우드)에서 EXE를 생성해 다운로드할 수 있습니다.

## 사용법
1. 이 폴더 통째로 새 GitHub 저장소에 업로드
2. 저장소 탭에서 **Actions** → 상단의 **I understand... Enable** (처음 1회)
3. 왼쪽 목록에서 **build-exe** 워크플로 선택 → **Run workflow** 버튼 클릭
4. 2~4분 후 실행이 끝나면, 작업 상세 페이지 하단 **Artifacts**에서 `NaverShoppingConnect_exe` 다운로드
5. 압축 풀면 `NaverShoppingConnect.exe`가 들어 있습니다. 더블클릭하여 실행

__참고:__ 첫 실행 시 SmartScreen 경고가 보이면 **추가 정보 → 실행**을 선택하세요.
