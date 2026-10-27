// The assessment report as a file (F6: exportable or printable). The backend
// writes one self-contained, print-ready HTML document; this downloads it,
// or prints it from a hidden frame (the print dialog also saves it as PDF).

import { apiGetFile } from '../../api/client';

const FRAME_STYLE = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0';

// Fetch the report document as a temporary local address.
async function reportUrl(interviewId) {
  return URL.createObjectURL(await apiGetFile(`/interviews/${interviewId}/report/export`));
}

// Save the report as an HTML file.
export async function downloadReport(interviewId, fileName) {
  const url = await reportUrl(interviewId);
  Object.assign(document.createElement('a'), { href: url, download: fileName }).click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Open the browser's print dialog for the report (also "Save as PDF").
export async function printReport(interviewId) {
  const url = await reportUrl(interviewId);
  const frame = Object.assign(document.createElement('iframe'), { src: url, title: 'Assessment report' });
  frame.style.cssText = FRAME_STYLE;
  frame.onload = () => {
    frame.contentWindow.focus();
    frame.contentWindow.print();
    setTimeout(() => {
      frame.remove();
      URL.revokeObjectURL(url);
    }, 60_000);
  };
  document.body.appendChild(frame);
}
