# Error Handling in Duke Energy Rate Comparison Tool

## User-Friendly Error Messages

The web application provides clear, helpful error messages for various scenarios:

### 1. **No File Selected**
**When:** User clicks "Analyze Rates" without selecting a file
**Error:** "Please select a file"
**Type:** JavaScript validation (instant feedback)

### 2. **Wrong File Type**
**When:** User uploads a non-XML file (e.g., .pdf, .csv, .txt)
**Error:** "Invalid file type. Please upload an XML file from Duke Energy Green Button"
**HTTP Code:** 400 (Bad Request)

### 3. **Empty or Invalid XML**
**When:** XML file is corrupted or not properly formatted
**Error:** "Invalid XML file format. The file appears to be corrupted or not a valid XML file. Please download a fresh copy from Duke Energy."
**HTTP Code:** 400 (Bad Request)

### 4. **No Energy Data Found**
**When:** XML file doesn't contain the expected Green Button data structure
**Error:** "No energy usage data found in the XML file. Please ensure you've uploaded a valid Duke Energy Green Button file."
**HTTP Code:** 400 (Bad Request)

### 5. **Insufficient Data**
**When:** XML file has data but less than 1 day worth (< 48 readings)
**Error:** "Insufficient data: only X readings found. Need at least 1 day of usage data for analysis."
**HTTP Code:** 400 (Bad Request)

### 6. **Missing Required Fields**
**When:** XML is missing critical fields (meter info, timestamps, values, etc.)
**Error:** "Invalid Green Button file format: Missing required field 'field_name'. Please ensure you downloaded the file correctly from Duke Energy."
**HTTP Code:** 400 (Bad Request)

### 7. **File Too Large**
**When:** User uploads a file larger than 16MB
**Error:** Flask will reject the upload automatically
**HTTP Code:** 413 (Request Entity Too Large)

### 8. **Network/Processing Errors**
**When:** Unexpected errors during processing
**Error:** "Unexpected error processing file: [error details]. Please ensure you uploaded a valid Duke Energy Green Button XML file."
**HTTP Code:** 500 (Internal Server Error)

---

## How Error Messages Are Displayed

1. **Red error box** appears below the upload section
2. **Loading spinner** disappears
3. **Previous results** (if any) remain visible
4. **User can try again** with a different file

---

## Error Message Design Principles

✅ **Clear:** Tell the user exactly what went wrong
✅ **Actionable:** Explain what they should do next
✅ **Friendly:** No technical jargon or scary stack traces
✅ **Specific:** Different messages for different problems
✅ **Helpful:** Point them to the solution (re-download, check file type, etc.)

---

## Testing Error Scenarios

You can test different error scenarios:

```bash
# 1. Wrong file type
curl -F "file=@test.pdf" http://localhost:5000/upload

# 2. Invalid XML
echo "not xml" > test.xml
curl -F "file=@test.xml" http://localhost:5000/upload

# 3. Empty XML
echo "<root></root>" > test.xml
curl -F "file=@test.xml" http://localhost:5000/upload
```

---

## Example Error Response (JSON)

```json
{
  "success": false,
  "error": "No energy usage data found in the XML file. Please ensure you've uploaded a valid Duke Energy Green Button file."
}
```

The JavaScript frontend displays this error message to the user in a red error box.
