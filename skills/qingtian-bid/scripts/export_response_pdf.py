"""Export and check the unsigned PDF rendition of the approved response.

INPUT: project DOCX, ready gate report, current rule card and image build report.
OUTPUT: output/施工组织设计.pdf and review/pdf-delivery.json, bound to the source and PDF hashes.
POS: after the DOCX gates, before submission. Uses local Word/WPS and pypdf; never rewrites a signed input.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

from check_qingtian_final import REPORT_FILE, finished_headings
from office_bridge import export_pdf_via_office
from project_cards import FINISHED_DOCX, RULE_CARD_FILE, file_sha256, load_json, load_project, now_text
from report_page_numbers import b2_hits, normalize, page_limit
from visual_assets import visual_dependency_issues

FINISHED_PDF = Path(FINISHED_DOCX).with_suffix('.pdf')
PDF_REPORT = Path('review/pdf-delivery.json')
SCHEMA = 'qingtian-pdf-delivery/1'
# Drop metadata from the page tree and resources as well as the document catalog.
PRIVATE_KEYS = frozenset(('/Metadata', '/PieceInfo', '/LastModified', '/AF', '/Thumb', '/AA'))
PAGE_EXCLUSIONS = ['/Annots', '/B', '/StructParents', '/Parent', *sorted(PRIVATE_KEYS)]


def pdf_objects(root):
    """Walk the reachable objects once, including indirect objects and resource streams."""
    pending, seen = [root], set()
    while pending:
        obj = pending.pop()
        if isinstance(obj, IndirectObject):
            key = (obj.idnum, obj.generation)
            if key in seen:
                continue
            seen.add(key)
            obj = obj.get_object()
        if isinstance(obj, DictionaryObject):
            yield obj
            pending.extend(obj.values())
        elif isinstance(obj, ArrayObject):
            pending.extend(obj)


def page_content(reader: PdfReader) -> list[str]:
    return [normalize(page.extract_text() or '') for page in reader.pages]


def unsigned_root(reader: PdfReader) -> DictionaryObject:
    if reader.is_encrypted:
        raise ValueError('PDF 已加密，请从未签章的终稿重新导出')
    root = reader.trailer['/Root']
    for obj in pdf_objects(root):
        if obj.get('/Type') in ('/Sig', '/DocTimeStamp') or obj.get('/FT') == '/Sig' or '/ByteRange' in obj:
            raise ValueError('PDF 已含数字签名或签名域，请从未签章的终稿重新导出')
    return root


def sanitize_export(raw: Path, target: Path) -> list[str]:
    reader = PdfReader(raw)
    root = unsigned_root(reader)
    original_text = page_content(reader)
    if not any(original_text):
        raise ValueError('导出的 PDF 没有可检索正文')
    # Copy only page content to a new file, so stale metadata, attachments, forms,
    # annotations and earlier revisions are not retained as unreachable objects.
    for obj in pdf_objects(root):
        for key in PRIVATE_KEYS:
            obj.pop(key, None)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page, excluded_keys=PAGE_EXCLUSIONS)
    # Older supported pypdf releases expose add_metadata but no metadata setter.
    if getattr(getattr(type(writer), 'metadata', None), 'fset', None):
        writer.metadata = None
    else:
        writer.add_metadata({'/Producer': ''})
    writer.write(target)
    clean = PdfReader(target)
    if (any((clean.metadata or {}).values()) or '/ID' in clean.trailer
            or any(PRIVATE_KEYS.intersection(obj) for obj in pdf_objects(clean.trailer['/Root']))):
        raise ValueError('PDF 元数据清理后仍有残留')
    if page_content(clean) != original_text:
        raise ValueError('清理前后 PDF 页数或正文不同')
    return original_text


def pdf_delivery_issues(project: Path, docx_sha: str, *, reviewed: bool = True) -> list[str]:
    pdf, report = project / FINISHED_PDF, project / PDF_REPORT
    if not pdf.is_file() or not report.is_file():
        return ['尚未导出清理后的 PDF：运行 export_response_pdf.py <项目目录>']
    try:
        record = load_json(report, 'PDF 交付记录')
    except ValueError as exc:
        return [str(exc)]
    if (record.get('schema') != SCHEMA or record.get('docx_sha256') != docx_sha
            or record.get('pdf_sha256') != file_sha256(pdf)):
        return ['PDF 或来源 DOCX 在导出后发生变化，请重新导出并逐页检查']
    if reviewed and not record.get('reviewed_at'):
        return ['PDF 尚未记录逐页检查，请检查后运行 export_response_pdf.py <项目目录> --reviewed']
    pages = record.get('pages')
    if type(pages) is not int or pages <= 0:
        return ['PDF 交付记录缺少有效页数，请重新导出']
    if b2_hits({'total_pages': pages, 'page_limit': page_limit(load_json(project / RULE_CARD_FILE, '规则卡'))}):
        return ['交付 PDF 页数不符合当前招标要求，请重新核对篇幅并导出']
    return []


def export_pdf(project: Path, office: str = 'auto') -> dict:
    from final_gate import stage7_issues

    project, state = load_project(project)
    issues = stage7_issues(project, state)
    if issues:
        raise ValueError('DOCX 尚未通过门禁：' + issues[0])
    source = project / FINISHED_DOCX
    gate = load_json(project / REPORT_FILE, '门禁报告')
    source_sha = gate['docx_sha256']
    with ZipFile(source) as archive:
        if any(name.lower().startswith('_xmlsignatures/') for name in archive.namelist()):
            raise ValueError('DOCX 已签章，请使用签章前的终稿导出')
    build = load_json(source.with_suffix('.build-report.json'), '构建报告')
    target, report = project / FINISHED_PDF, project / PDF_REPORT
    if target.is_file():
        unsigned_root(PdfReader(target))
    report.parent.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=target.parent) as folder:
        folder = Path(folder)
        copy, raw, clean = folder / 'response.docx', folder / 'export.pdf', folder / 'clean.pdf'
        shutil.copyfile(source, copy)
        if file_sha256(copy) != source_sha:
            raise ValueError('DOCX 与门禁报告不一致')
        engine = export_pdf_via_office(copy, raw, office)
        if not engine:
            raise ValueError('未能用 Word/WPS 导出完整 PDF，请检查本机 Office 后重试')
        texts = sanitize_export(raw, clean)
        all_text = ''.join(texts)
        required_texts = finished_headings(copy) + [normalize(item['caption']) for item in build.get('image_sources', [])
                                                    if item.get('caption')]
        if any(phrase not in all_text for phrase in required_texts):
            raise ValueError('PDF 有章节标题或图题未保留为可检索文本，请检查导出效果')
        limits = page_limit(load_json(project / RULE_CARD_FILE, '规则卡'))
        hits = b2_hits({'total_pages': len(texts), 'page_limit': limits})
        if hits:
            raise ValueError(hits[0]['message'])
        if file_sha256(source) != source_sha or visual_dependency_issues(build, source):
            raise ValueError('导出期间 DOCX 或图片发生变化，请重新核对')
        record = {'schema': SCHEMA, 'docx_sha256': source_sha, 'pdf_sha256': file_sha256(clean),
                  'pdf': FINISHED_PDF.as_posix(), 'pages': len(texts), 'engine': engine, 'exported_at': now_text()}
        candidate = folder / 'report.json'
        candidate.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.replace(clean, target)
        os.replace(candidate, report)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description='导出并验收匿名属性清理后的完整施组 PDF。')
    parser.add_argument('project', type=Path)
    parser.add_argument('--office', choices=('auto', 'word', 'wps'), default='auto')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--check', action='store_true', help='检查最终 PDF 及逐页检查记录是否对应当前 DOCX。')
    modes.add_argument('--reviewed', action='store_true', help='逐页检查 PDF 后，记录当前文件已经检查。')
    args = parser.parse_args()
    try:
        project, state = load_project(args.project)
        if args.check or args.reviewed:
            from final_gate import stage7_issues

            issues = stage7_issues(project, state) or pdf_delivery_issues(
                project, file_sha256(project / FINISHED_DOCX), reviewed=args.check)
            if issues:
                raise ValueError(issues[0])
            report = project / PDF_REPORT
            record = load_json(report, 'PDF 交付记录')
            if args.reviewed:
                record['reviewed_at'] = now_text()
                report.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            record = export_pdf(project, args.office)
    except (OSError, ValueError, PdfReadError, BadZipFile) as exc:
        print(f'PDF 交付检查失败：{exc}')
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
