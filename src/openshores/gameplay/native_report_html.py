
from __future__ import annotations


def _native_test_report_html():
    green = '#8fd58f'; red = '#e08f8f'; white = '#ffffff'; muted = '#9fb0cc'
    def sec(title):
        return f'<p><font color="{white}"><b>{title}</b></font><br>'
    rows = []
    def bankrow(lbl, val, indent=True, hdr=None):
        pad = '&nbsp;&nbsp;&nbsp;&nbsp;' if indent else ''
        if hdr:
            return (f'<tr><td bgcolor="{hdr}"><font color="#eef0dd"><b>{lbl}</b></font></td>'
                    f'<td bgcolor="{hdr}" align="right"><font color="#eef0dd"><b>{val}</b></font></td></tr>')
        return (f'<tr><td>{pad}{lbl}</td><td align="right">{val}</td></tr>')
    html = (
        '<html><body style="color:#c6d0e2;">'
        f'<p><font color="{muted}">2020-11-04 18:14</font><br>'
        f'<font color="{white}" size="4"><b>City Status Report</b></font></p>'
        + '</table></body></html>'
    )
    return html
