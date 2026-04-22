# ITSM Knowledge Base - Ticket Classification and Procedures

## Priority Levels

### P1 - Critical
- **Definition**: Complete system outage or critical functionality unavailable
- **Impact**: Affects all users or critical business operations
- **Response Time**: 15 minutes
- **Resolution Target**: 4 hours
- **Examples**:
  - Complete network outage
  - Production database down
  - Authentication system failure
  - VPN gateway completely unavailable

### P2 - High
- **Definition**: Major functionality impaired, significant user impact
- **Impact**: Affects multiple users or important business functions
- **Response Time**: 1 hour
- **Resolution Target**: 8 hours
- **Examples**:
  - Partial VPN connectivity issues
  - Email service degraded
  - Critical application slow performance
  - Portal login intermittent failures

### P3 - Medium
- **Definition**: Minor functionality issue, limited user impact
- **Impact**: Affects individual users or non-critical functions
- **Response Time**: 4 hours
- **Resolution Target**: 24 hours
- **Examples**:
  - Single user cannot access shared drive
  - Non-critical application error
  - Printer connectivity issue
  - Password reset request

### P4 - Low
- **Definition**: Enhancement request or cosmetic issue
- **Impact**: Minimal or no business impact
- **Response Time**: 8 hours
- **Resolution Target**: 5 business days
- **Examples**:
  - Feature requests
  - Documentation updates
  - UI cosmetic issues
  - General inquiries

## Ticket Categories

### Hardware
- Physical equipment failures
- Workstation issues
- Server hardware problems
- Peripheral device malfunctions
- **Assigned Team**: Infrastructure Team

### Software
- Application errors
- Software installation issues
- License problems
- Application performance issues
- **Assigned Team**: Backend Team or Frontend Team (depending on application)

### Network
- Connectivity problems
- VPN issues
- Firewall configuration
- DNS problems
- Bandwidth issues
- **Assigned Team**: Infrastructure Team

### Access/Security
- Login failures
- Permission issues
- Account lockouts
- Password resets
- Security incidents
- **Assigned Team**: Security Team

## Escalation Procedures

### When to Escalate
1. Issue not resolved within SLA timeframe
2. Requires specialized expertise
3. Affects critical business operations
4. Security incident detected
5. Multiple related incidents indicate systemic issue

### Escalation Path
1. **L1 Support** → **L2 Support** (after 2 hours for P1, 4 hours for P2)
2. **L2 Support** → **Team Lead** (if specialized knowledge needed)
3. **Team Lead** → **Manager** (for critical business impact)
4. **Manager** → **Director** (for major incidents affecting entire organization)

## Common IT Issues and Resolutions

### VPN Connection Issues
- **Priority**: P2 (High) if affecting multiple users, P3 (Medium) for single user
- **Category**: Network
- **Team**: Infrastructure
- **Common Causes**:
  - Expired certificates
  - Firewall blocking VPN ports
  - Client software outdated
  - Network configuration changes
- **Resolution Steps**:
  1. Verify user credentials
  2. Check VPN client version
  3. Verify firewall rules
  4. Test from different network
  5. Reinstall VPN client if needed

### Portal Login Failures
- **Priority**: P2 (High) if widespread, P3 (Medium) for individual
- **Category**: Access/Security
- **Team**: Security Team
- **Common Causes**:
  - Account locked after failed attempts
  - Password expired
  - MFA issues
  - Session timeout
- **Resolution Steps**:
  1. Verify account status
  2. Check for account lockout
  3. Reset password if expired
  4. Verify MFA configuration
  5. Clear browser cache/cookies

### Email Service Issues
- **Priority**: P1 (Critical) if complete outage, P2 (High) if degraded
- **Category**: Software
- **Team**: Backend Team
- **Common Causes**:
  - Mail server overload
  - Storage quota exceeded
  - Network connectivity issues
  - Configuration errors
- **Resolution Steps**:
  1. Check mail server status
  2. Verify user mailbox quota
  3. Test SMTP/IMAP connectivity
  4. Review server logs
  5. Restart mail services if needed

## SLA Requirements

### Response Times
- P1 (Critical): 15 minutes
- P2 (High): 1 hour
- P3 (Medium): 4 hours
- P4 (Low): 8 hours

### Resolution Times
- P1 (Critical): 4 hours
- P2 (High): 8 hours
- P3 (Medium): 24 hours
- P4 (Low): 5 business days

### Business Hours
- Standard Support: Monday-Friday, 8 AM - 6 PM EST
- After-Hours Support: Available for P1 and P2 incidents only
- Weekend Support: On-call for critical (P1) incidents only

## Incident Logging Requirements

### Required Information
1. **Subject**: Clear, concise description of issue
2. **Description**: Detailed symptom description
3. **User Information**: Name, email, phone, department
4. **Impact**: Number of users affected, business impact
5. **Priority**: Based on impact and urgency
6. **Category**: Hardware, Software, Network, or Access
7. **Steps to Reproduce**: If applicable
8. **Error Messages**: Exact text of any errors
9. **When Started**: Date and time issue began

### Callback Triggers
Create callback request for:
- P1 (Critical) incidents - Always
- P2 (High) incidents - If user requests or if complex issue
- P3 (Medium) incidents - Only if user specifically requests
- P4 (Low) incidents - Not required
