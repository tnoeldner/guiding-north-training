# UND Housing Information Integration Summary

## Overview
All scenarios generated in the Guiding North Training application now reference authentic UND Housing & Residence Life information, making training scenarios realistic and grounded in actual campus operations.

## What Was Integrated

### 1. **UND Housing Context Constant**
A comprehensive `UND_HOUSING_CONTEXT` constant was added to `app.py` containing:

#### **Residence Halls**
- Suite Style: McVey Hall, West Hall, Brannon Hall, Noren Hall, Selke Hall
- Community Style: Smith Hall, Johnstone Hall (Smith/Johnstone complex)
- Apartment Style: University Place, Swanson Hall

#### **Apartment Locations**
- Berkeley Drive, Carleton Court, Hamline Square, Mt. Vernon/Williamsburg, Swanson Complex, Tulane Court, Virginia Rose, 3904 University Ave

#### **Key Policies & Procedures**
- **Guest Policy**: Max 3 consecutive nights, 6 nights total per month, must be escorted 24/7, roommate consent required
- **Quiet Hours**: Sun-Thu 10 PM-10 AM, Fri-Sat 12 AM-10 AM, Courtesy Hours 24/7
- **Lockout Fees**: $10 business hours, $25 after hours, $75 key recore
- **Room Changes**: Frozen first 2 weeks, RD approval required, $100+ unauthorized move fine
- **Alcohol/Drugs**: Under 21 prohibited, 21+ in all-age rooms only, no paraphernalia
- **Maintenance**: Routine within 2 business days via portal, emergency calls to RA on Duty
- **Move-Out**: 60-day notice required, $165 modem removal fine

#### **Housing Contact Information**
- Phone: 701.777.4251
- Email: housing@UND.edu
- Office Hours: Mon-Fri 8:00 AM - 4:30 PM

#### **Housing Rates (2025-2026)**
- Residence Hall Double: $5,100-$6,180/year
- Residence Hall Single: $5,900-$7,300/year
- Apartments One Bedroom: $735-$845/month
- Apartments Two Bedroom: $830-$935/month
- Apartments Three Bedroom: $1,010-$1,400/month

### 2. **Scenario Simulator Integration**
The Scenario Simulator (free practice scenarios) now includes UND Housing Context in its prompt:
- Requires scenarios reference real UND halls and apartments
- Mandates authentic policy details (fees, quiet hours, procedures)
- Ensures realistic fee amounts are used
- Encourages scenarios to feel like actual UND Housing situations

### 3. **Assign Scenarios Integration**
The Assign Scenarios feature (supervisor-assigned targeted training) now:
- Includes complete UND Housing Context in generation prompt
- Requires scenarios use real building names and locations
- Mandates authentic policy references with correct fee amounts
- Emphasizes immersive details (specific times, dates, buildings)
- Makes scenarios reflective of actual roles and responsibilities

## Enhanced Realism Features

### Building Specificity
- Scenarios now mention specific halls (e.g., "McVey Hall" instead of "a residence hall")
- Apartment locations referenced by actual names
- Role-specific building assignments where applicable

### Authentic Fee Amounts
- Lockout fees: $10/$25 (matching actual charges)
- Key recore: $75 (reflects mandatory security replacement)
- Unauthorized moves: $100+
- Modem removal: $165 (specific penalty)

### Real Policies in Scenarios
- Guest limits and escort requirements
- Quiet hours enforcement situations
- Room change procedures and restrictions
- Maintenance request processes
- Housing contract implications

### Campus Resources
- References to Wilkerson Service Center
- Housing Self-Service portal procedures
- RA on Duty after-hours contact
- Housing Office contact information

## Data Sources
Information sourced from:
- UND Housing & Residence Life Knowledge Base (operational protocols)
- UND Housing website (https://und.edu/student-life/housing/)
- Current 2025-2026 housing rates and policies

## Impact on Staff Training
- **More Authentic Scenarios**: Staff encounter realistic situations they'll actually face
- **Real Building Knowledge**: Familiarity with actual residence halls and apartments
- **Policy Accuracy**: Correct procedures and fee amounts reduce confusion
- **Confidence Building**: Training scenarios match real-world operations

## Implementation Details

### Code Changes
- Added `UND_HOUSING_CONTEXT` constant (38 lines) with comprehensive housing information
- Updated Scenario Simulator prompt to include UND Housing Context
- Updated Assign Scenarios prompt to emphasize realistic UND housing details
- No database schema changes required - information integrated into prompts

### Backward Compatibility
- All existing scenarios continue to work
- New scenarios generated with authentic information
- Staff see improved realism without system changes

## Testing
- Application verified to run without errors
- All scenario generation endpoints functional
- UND Housing Context properly integrated into both simulator and assigned scenarios

## Future Enhancement Opportunities
- Add specific building amenities to context
- Include seasonal considerations (winter break housing)
- Reference recent policy updates
- Add staff-specific facility access details
- Include emergency procedures and resources

---
**Commit**: 156d41c - Integrate authentic UND housing information into scenario generation
**Date**: February 5, 2026
