"""A very small .xlsx writer, and the combined-sheet layout we share with volunteers.

Why hand-rolled: an .xlsx is a zip of XML, and the only formatting this project
needs is bold text, one fill colour, a font size, column widths and hyperlinks.
Pyodide ships no spreadsheet library, and fetching one from PyPI at click time
would make the web app depend on the network for a core feature. This keeps it
working offline, which is the point of the whole design.

The layout matches the sheet the observatory already hands round: every telescope
stacked down one sheet, each with a coloured title, a header row, its schedule, a
blank line, then its alternate targets.
"""

import zipfile

#One colour per telescope section, so a volunteer can find their block by
#colour alone. The first three are the Google palette the shared sheet already
#uses; the rest keep neighbouring sections in different hues and stay light
#enough for the bold black title text to read against them. There are more
#colours here than the largest roster target_lists allows, so no two telescopes
#on one night share one; beyond that the list just wraps round.
TITLE_FILLS = [
    "FFEA4335",  # red
    "FF34A853",  # green
    "FFFBBC04",  # yellow
    "FF4FC3F7",  # light blue
    "FFBA68C8",  # light purple
    "FFFFA726",  # orange
    "FF4DD0E1",  # cyan
    "FFA1887F",  # light brown
    "FFAED581",  # light green
    "FFF06292",  # pink
    "FF9FA8DA",  # periwinkle
    "FFE6EE9C",  # lime
    "FFBCAAA4",  # taupe
]

#style indices into the cellXfs table written by _styles_xml()
STYLE_PLAIN = 0
STYLE_BOLD = 1
STYLE_LINK = 2
#the title styles follow, one per colour: STYLE_TITLE_BASE + colour index
STYLE_TITLE_BASE = 3


def title_style(index):
    """cellXfs index for the title row of the index-th telescope."""
    return STYLE_TITLE_BASE + (index % len(TITLE_FILLS))

#column widths, keyed by 1-based column number, taken from the existing sheet
DEFAULT_WIDTHS = {1: 18.0, 3: 14.9, 5: 18.0, 6: 20.5, 8: 72.0}


def _esc(text):
    """XML-escape a string. Outreach URLs contain & and ?, so this matters."""
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _col_letter(index):
    """1 -> A, 27 -> AA."""
    letters = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _is_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    return False


class Sheet:
    """Rows of cells, accumulated then serialised.

    A cell is a plain value, or a dict {"value", "style", "link"}.
    """

    def __init__(self, name="Schedule", widths=None):
        self.name = name
        self.widths = dict(DEFAULT_WIDTHS if widths is None else widths)
        self.rows = []

    def add(self, cells):
        self.rows.append(list(cells))

    def blank(self):
        self.rows.append([])

    def _cells_xml(self, row_number, cells, links):
        out = []
        for i, cell in enumerate(cells, start=1):
            if isinstance(cell, dict):
                value, style, link = cell.get("value"), cell.get("style", STYLE_PLAIN), cell.get("link")
            else:
                value, style, link = cell, STYLE_PLAIN, None

            ref = f"{_col_letter(i)}{row_number}"

            if value is None or value == "":
                #an empty cell still has to be written when it carries a fill,
                #which is how a title row gets coloured across the full table
                if style:
                    out.append(f'<c r="{ref}" s="{style}"/>')
                continue
            if link:
                links.append((ref, link))
                style = STYLE_LINK

            attrs = f'r="{ref}"' + (f' s="{style}"' if style else "")
            if _is_number(value):
                out.append(f'<c {attrs}><v>{value}</v></c>')
            else:
                out.append(f'<c {attrs} t="inlineStr"><is><t>{_esc(value)}</t></is></c>')
        return "".join(out)

    def to_xml(self):
        links = []
        body = []
        for n, cells in enumerate(self.rows, start=1):
            inner = self._cells_xml(n, cells, links)
            body.append(f'<row r="{n}">{inner}</row>' if inner else f'<row r="{n}"/>')

        cols = "".join(
            f'<col min="{c}" max="{c}" width="{w}" customWidth="1"/>'
            for c, w in sorted(self.widths.items())
        )

        #order matters in the schema: cols, then sheetData, then hyperlinks
        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
            f'<cols>{cols}</cols>' if cols else "",
            f'<sheetData>{"".join(body)}</sheetData>',
        ]
        if links:
            hl = "".join(
                f'<hyperlink ref="{ref}" r:id="rId{i + 1}"/>'
                for i, (ref, _) in enumerate(links)
            )
            parts.append(f'<hyperlinks>{hl}</hyperlinks>')
        parts.append('</worksheet>')

        return "".join(parts), links


def _styles_xml():
    #Excel requires fill 0 to be "none" and fill 1 to be "gray125"; the telescope
    #colours start at index 2, and each gets a matching cellXfs entry so a title
    #row can be referenced by style alone.
    colour_fills = "".join(
        f'<fill><patternFill patternType="solid"><fgColor rgb="{rgb}"/>'
        '<bgColor indexed="64"/></patternFill></fill>'
        for rgb in TITLE_FILLS
    )

    title_xfs = "".join(
        f'<xf numFmtId="0" fontId="2" fillId="{2 + i}" borderId="0" xfId="0"'
        ' applyFont="1" applyFill="1"/>'
        for i in range(len(TITLE_FILLS))
    )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="4">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="13"/><name val="Calibri"/></font>'
        '<font><u/><sz val="11"/><color rgb="FF0000FF"/><name val="Calibri"/></font>'
        '</fonts>'
        f'<fills count="{2 + len(TITLE_FILLS)}">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        f'{colour_fills}'
        '</fills>'
        '<borders count="1"><border/></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        f'<cellXfs count="{3 + len(TITLE_FILLS)}">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        f'{title_xfs}'
        '</cellXfs>'
        #optional in the schema, but readers warn without a named Normal style
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        '<dxfs count="0"/>'
        '<tableStyles count="0" defaultTableStyle="TableStyleMedium9"'
        ' defaultPivotStyle="PivotStyleLight16"/>'
        '</styleSheet>'
    )


def write_xlsx(sheet):
    """Serialise one Sheet into .xlsx bytes."""
    import io

    sheet_xml, links = sheet.to_xml()

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{_esc(sheet.name)}" sheetId="1" r:id="rId1"/></sheets>'
        '</workbook>'
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        zf.writestr("xl/styles.xml", _styles_xml())
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

        if links:
            rels = "".join(
                f'<Relationship Id="rId{i + 1}"'
                ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"'
                f' Target="{_esc(target)}" TargetMode="External"/>'
                for i, (_, target) in enumerate(links)
            )
            zf.writestr(
                "xl/worksheets/_rels/sheet1.xml.rels",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'{rels}</Relationships>'
            )

    return buf.getvalue()


def combined_sheet(sections, sheet_name="Schedule"):
    '''
    Lay every telescope out down one sheet, the way the shared spreadsheet reads.

    sections : list of (title, DataFrame) in the order they should appear. Each
        frame is what code.build_catalog_frames() returns, so it already carries
        the schedule rows, the "Alternate Targets" separator and the alternates.

    Returns a Sheet ready for write_xlsx().
    '''
    sheet = Sheet(name=sheet_name)

    for index, (title, frame) in enumerate(sections):
        if index:
            sheet.blank()

        columns = list(frame.columns)

        #colour the whole width of the table, not just the cell with the name in
        style = title_style(index)
        sheet.add([{"value": title if c == 0 else "", "style": style}
                   for c in range(len(columns))])

        sheet.add([{"value": c, "style": STYLE_BOLD} for c in frame.columns])
        link_columns = {c for c in ("Outreach Info", "Visibility Link") if c in columns}

        for _, row in frame.iterrows():
            #the alternates block reads better with air above it
            if str(row[columns[0]]).strip() == "Alternate Targets":
                sheet.blank()
                sheet.add([{"value": "Alternate Targets", "style": STYLE_BOLD}])
                continue

            cells = []
            for c in columns:
                value = row[c]
                if value is None or str(value) == "" or str(value) == "nan":
                    cells.append("")
                elif c == "Elevation":
                    #keep it numeric so the column can be sorted
                    cells.append(float(value))
                elif c in link_columns and str(value).startswith("http"):
                    cells.append({"value": str(value), "link": str(value)})
                else:
                    cells.append(str(value))
            sheet.add(cells)

    return sheet
