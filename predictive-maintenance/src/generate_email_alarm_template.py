def create_email_body(alarm_severity, alarm_type, time_fmt):
    """
    Create a styled HTML email body for alarm notifications.
    
    Args:
        alarm_severity: Severity level of the alarm (e.g., "Critical", "High", "Medium", "Low")
        alarm_type: Type of alarm (e.g., "System Error", "Security Alert")
        time_fmt: Formatted timestamp of when the alarm started
    
    Returns:
        Tuple of (text_body, html_body) for email
    """
    
    # Determine color based on severity
    severity_colors = {
        'critical': '#dc3545',
        'high': '#fd7e14',
        'medium': '#ffc107',
        'low': '#17a2b8'
    }
    
    severity_lower = alarm_severity.lower()
    severity_color = severity_colors.get(severity_lower, '#6c757d')
    
    # Plain text version (fallback)
    text_body = (
        "Subject: New alarm assignment.\n\n"
        f"You got assigned a new alarm alert. {alarm_severity}.\n"
        f"Type: {alarm_type}\n"
        f"Started at: {time_fmt}\n\n"
        "AnalyticalBoard."
    )
    
    # HTML version with CSS styling
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background-color: #f4f4f4;
        }}
        .container {{
            max-width: 600px;
            margin: 20px auto;
            background-color: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #ffffff;
            padding: 30px 20px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
            font-weight: 600;
        }}
        .content {{
            padding: 40px 30px;
        }}
        .alert-banner {{
            background-color: {severity_color};
            color: #ffffff;
            padding: 15px 20px;
            border-radius: 6px;
            margin-bottom: 25px;
            font-weight: 600;
            font-size: 16px;
            text-align: center;
        }}
        .info-section {{
            background-color: #f8f9fa;
            border-left: 4px solid {severity_color};
            padding: 20px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
        .info-row {{
            display: flex;
            margin-bottom: 12px;
            align-items: baseline;
        }}
        .info-row:last-child {{
            margin-bottom: 0;
        }}
        .info-label {{
            font-weight: 600;
            color: #495057;
            min-width: 100px;
            font-size: 14px;
        }}
        .info-value {{
            color: #212529;
            font-size: 14px;
        }}
        .footer {{
            background-color: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            color: #6c757d;
            font-size: 14px;
            border-top: 1px solid #dee2e6;
        }}
        .footer-brand {{
            font-weight: 600;
            color: #495057;
        }}
        @media only screen and (max-width: 600px) {{
            .container {{
                margin: 0;
                border-radius: 0;
            }}
            .content {{
                padding: 30px 20px;
            }}
            .info-row {{
                flex-direction: column;
            }}
            .info-label {{
                margin-bottom: 4px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>New Alarm Assignment</h1>
        </div>
        
        <div class="content">
            <div class="alert-banner">
                Severity: {alarm_severity.upper()}
            </div>
            
            <p style="color: #495057; font-size: 15px; line-height: 1.6; margin-bottom: 25px;">
                You have been assigned a new alarm alert that requires your attention. 
                Please review the details below and take appropriate action.
            </p>
            
            <div class="info-section">
                <div class="info-row">
                    <span class="info-label">Severity:</span>
                    <span class="info-value">{alarm_severity}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Type:</span>
                    <span class="info-value">{alarm_type}</span>
                </div>
                <div class="info-row">
                    <span class="info-label">Started at:</span>
                    <span class="info-value">{time_fmt}</span>
                </div>
            </div>
        </div>
        
        <div class="footer">
            <span class="footer-brand">AnalyticalBoard</span>
        </div>
    </div>
</body>
</html>
"""
    
    return text_body, html_body


# Example usage:
# text, html = create_email_body("Critical", "System Error", "2024-12-23 14:30:00")
# Then use these in your email sending function with both plain text and HTML parts