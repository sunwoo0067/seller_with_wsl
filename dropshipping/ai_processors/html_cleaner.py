
HTML 클리너 모듈
상품 상세 설명 HTML을 정제하고 불필요한 태그를 제거

from typing import Dict, Any, Optional
from bs4 import BeautifulSoup, NavigableString
from loguru import logger

class HTMLCleaner:
    """HTML 클리너"""

    def __init__(self):
        # 허용할 태그와 속성
        self.allowed_tags = [
            'p', 'br', 'b', 'strong', 'i', 'em', 'u', 's', 'strike',
            'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
            'a', 'img', 'table', 'tr', 'td', 'th', 'tbody', 'thead',
            'div', 'span', 'pre', 'code', 'blockquote',
        ]
        self.allowed_attrs = {
            'a': ['href', 'title'],
            'img': ['src', 'alt', 'width', 'height'],
            'table': ['border', 'cellpadding', 'cellspacing', 'width'],
            'td': ['colspan', 'rowspan', 'width', 'height'],
            'th': ['colspan', 'rowspan', 'width', 'height'],
            '*': ['style', 'class', 'id'], # 모든 태그에 허용할 공통 속성
        }
        # 제거할 패턴 (예: 특정 스크립트, 인라인 스타일 등)
        self.remove_patterns = [
            re.compile(r'<script.*?>.*?</script>', re.DOTALL | re.IGNORECASE),
            re.compile(r'on[a-z]+\s*=\s*['"][^'"]*['"]', re.IGNORECASE), # JS 이벤트 핸들러
        ]

    def clean_html(self, html_content: str) -> str:
        """
        HTML 콘텐츠를 정제하고 불필요한 태그 및 속성을 제거합니다.
        
        Args:
            html_content: 원본 HTML 문자열
            
        Returns:
            정제된 HTML 문자열
        """
        if not html_content:
            return ""

        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. 특정 패턴 제거
        for pattern in self.remove_patterns:
            html_content = pattern.sub('', html_content)
        soup = BeautifulSoup(html_content, 'html.parser') # 패턴 제거 후 다시 파싱

        # 2. 허용되지 않는 태그 제거
        for tag in soup.find_all(True):
            if tag.name not in self.allowed_tags:
                tag.unwrap() # 태그만 제거하고 내용은 유지

        # 3. 허용되지 않는 속성 제거
        for tag in soup.find_all(True):
            if tag.name in self.allowed_attrs:
                allowed_for_tag = self.allowed_attrs[tag.name]
            else:
                allowed_for_tag = self.allowed_attrs.get('*', [])
            
            attrs_to_remove = [
                attr for attr in tag.attrs if attr not in allowed_for_tag
            ]
            for attr in attrs_to_remove:
                del tag[attr]

        # 4. 빈 태그 제거 (옵션)
        for tag in soup.find_all():
            if not tag.contents and not tag.is_empty_element:
                tag.extract() # 태그와 내용 모두 제거

        # 5. 불필요한 공백 및 줄바꿈 정리
        cleaned_text = str(soup)
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip() # 여러 공백을 하나로
        cleaned_text = re.sub(r'\n\s*\n', '\n\n', cleaned_text) # 여러 줄바꿈을 하나로

        logger.debug("HTML 정제 완료")
        return cleaned_text

    def extract_text(self, html_content: str) -> str:
        """
        HTML에서 텍스트만 추출합니다.
        
        Args:
            html_content: 원본 HTML 문자열
            
        Returns:
            추출된 텍스트 문자열
        """
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text(separator=' ', strip=True)

    def remove_images(self, html_content: str) -> str:
        """
        HTML에서 모든 이미지 태그를 제거합니다.
        
        Args:
            html_content: 원본 HTML 문자열
            
        Returns:
            이미지 태그가 제거된 HTML 문자열
        """
        if not html_content:
            return ""
        soup = BeautifulSoup(html_content, 'html.parser')
        for img_tag in soup.find_all('img'):
            img_tag.extract()
        return str(soup)

    def replace_image_urls(self, html_content: str, url_map: Dict[str, str]) -> str:
        """
        HTML 내 이미지 URL을 교체합니다.
        
        Args:
            html_content: 원본 HTML 문자열
            url_map: {원본 URL: 새 URL} 딕셔너리
            
        Returns:
            URL이 교체된 HTML 문자열
        """
        if not html_content or not url_map:
            return html_content
        
        soup = BeautifulSoup(html_content, 'html.parser')
        for img_tag in soup.find_all('img'):
            src = img_tag.get('src')
            if src and src in url_map:
                img_tag['src'] = url_map[src]
                logger.debug(f"이미지 URL 교체: {src} -> {url_map[src]}")
        return str(soup)
