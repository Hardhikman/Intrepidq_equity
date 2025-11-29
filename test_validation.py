"""
Test script for data validation functionality
"""

import sys
import os
sys.path.append(os.getcwd())

from tools.definitions import get_deep_financials_tool
from tools.validation import validate_data_completeness, format_validation_report


def test_validation():
    """Test validation with AAPL (should have high completeness)"""
    print("=" * 60)
    print("Testing Validation with AAPL (Expected: High Completeness)")
    print("=" * 60)
    
    # Get financial data
    result = get_deep_financials_tool.func("AAPL")
    
    if result['status'] == 'success':
        # Validate
        validation = validate_data_completeness(result['data'])
        
        # Display results
        print(f"\n✅ Completeness Score: {validation['completeness_score']}%")
        print(f"✅ Confidence Level: {validation['confidence_level']}")
        print(f"✅ Critical Metrics: {validation['available_critical']}/{validation['available_critical'] + len(validation['missing_critical'])}")
        
        # Display warnings
        if validation['warnings']:
            print("\n⚠️ Warnings:")
            for warning in validation['warnings']:
                print(f"  {warning}")
        
        # Display formatted report
        print("\n" + "=" * 60)
        print("FORMATTED REPORT")
        print("=" * 60)
        report = format_validation_report(validation, "AAPL")
        print(report)
        
        # Test passed if completeness > 80%
        if validation['completeness_score'] >= 80:
            print("\n✅ TEST PASSED - High data quality detected")
        else:
            print(f"\n⚠️ TEST WARNING - Completeness only {validation['completeness_score']}%")
    else:
        print(f"\n❌ TEST FAILED: {result.get('error_message')}")


def test_validation_with_incomplete_data():
    """Test validation with simulated incomplete data"""
    print("\n\n" + "=" * 60)
    print("Testing Validation with Incomplete Data")
    print("=" * 60)
    
    # Simulate incomplete data
    incomplete_data = {
        "ticker": "TEST",
        "current_price": 100.0,
        "market_cap": 1000000000,
        # Missing most metrics
    }
    
    validation = validate_data_completeness(incomplete_data)
    
    print(f"\n⚠️ Completeness Score: {validation['completeness_score']}%")
    print(f"⚠️ Confidence Level: {validation['confidence_level']}")
    print(f"⚠️ Missing Critical: {len(validation['missing_critical'])} metrics")
    
    # Display warnings
    if validation['warnings']:
        print("\n⚠️ Warnings:")
        for warning in validation['warnings']:
            print(f"  {warning}")
    
    # Test passed if low confidence is detected
    if validation['confidence_level'] == "Low":
        print("\n✅ TEST PASSED - Low confidence correctly detected")
    else:
        print(f"\n❌ TEST FAILED - Expected Low confidence, got {validation['confidence_level']}")


if __name__ == "__main__":
    test_validation()
    test_validation_with_incomplete_data()
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)
