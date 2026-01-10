/**
 * Project Aegis - IsoParser Unit Tests
 *
 * Tests the ISO 20022 XML parser for correct extraction
 * of payment data from pacs.008 and similar messages.
 */

#include <gtest/gtest.h>
#include "../../hft_core.hpp"

// =============================================================================
// Test Fixtures
// =============================================================================

class IsoParserTest : public ::testing::Test {
protected:
    PaymentData payment;

    void SetUp() override {
        memset(&payment, 0, sizeof(payment));
    }
};

// =============================================================================
// Valid XML Tests
// =============================================================================

TEST_F(IsoParserTest, ParseValidPacs008) {
    const char* xml = R"(<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pacs.008.001.08">
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId>
        <UETR>550e8400-e29b-41d4-a716-446655440000</UETR>
      </PmtId>
      <Dbtr>
        <Nm>Alice Smith</Nm>
      </Dbtr>
      <Cdtr>
        <Nm>Bob Jones</Nm>
      </Cdtr>
      <Amt>
        <InstdAmt Ccy="EUR">1500.00</InstdAmt>
      </Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_TRUE(IsoParser::parse(xml, strlen(xml), payment));

    EXPECT_STREQ(payment.uetr, "550e8400-e29b-41d4-a716-446655440000");
    EXPECT_STREQ(payment.debtor_name, "Alice Smith");
    EXPECT_STREQ(payment.creditor_name, "Bob Jones");
    EXPECT_STREQ(payment.currency, "EUR");
    EXPECT_EQ(payment.amount, 1500000000); // 1500.00 * 10^6
    EXPECT_TRUE(payment.valid_schema);
}

TEST_F(IsoParserTest, ParseValidFIToFI) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <FIToFICdtTrf>
    <CdtTrfTxInf>
      <PmtId>
        <EndToEndId>TXN-2024-001</EndToEndId>
      </PmtId>
      <Dbtr>
        <Nm>Corporate Ltd</Nm>
      </Dbtr>
      <Cdtr>
        <Nm>Supplier Inc</Nm>
      </Cdtr>
      <Amt>
        <InstdAmt Ccy="USD">50000.00</InstdAmt>
      </Amt>
    </CdtTrfTxInf>
  </FIToFICdtTrf>
</Document>)";

    EXPECT_TRUE(IsoParser::parse(xml, strlen(xml), payment));

    EXPECT_STREQ(payment.uetr, "TXN-2024-001");
    EXPECT_STREQ(payment.currency, "USD");
    EXPECT_EQ(payment.amount, 50000000000); // 50000.00 * 10^6
}

TEST_F(IsoParserTest, ParseGBPCurrency) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr-123</UETR></PmtId>
      <Dbtr><Nm>UK Sender</Nm></Dbtr>
      <Cdtr><Nm>UK Receiver</Nm></Cdtr>
      <Amt><InstdAmt Ccy="GBP">999.99</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_TRUE(IsoParser::parse(xml, strlen(xml), payment));
    EXPECT_STREQ(payment.currency, "GBP");
}

// =============================================================================
// Invalid XML Tests
// =============================================================================

TEST_F(IsoParserTest, RejectMalformedXml) {
    const char* xml = "This is not XML at all!";
    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectMissingDebtor) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Cdtr><Nm>Bob</Nm></Cdtr>
      <Amt><InstdAmt Ccy="EUR">100.00</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectMissingCreditor) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Dbtr><Nm>Alice</Nm></Dbtr>
      <Amt><InstdAmt Ccy="EUR">100.00</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectMissingAmount) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Dbtr><Nm>Alice</Nm></Dbtr>
      <Cdtr><Nm>Bob</Nm></Cdtr>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectZeroAmount) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Dbtr><Nm>Alice</Nm></Dbtr>
      <Cdtr><Nm>Bob</Nm></Cdtr>
      <Amt><InstdAmt Ccy="EUR">0</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectNegativeAmount) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Dbtr><Nm>Alice</Nm></Dbtr>
      <Cdtr><Nm>Bob</Nm></Cdtr>
      <Amt><InstdAmt Ccy="EUR">-500.00</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectInvalidCurrency) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Dbtr><Nm>Alice</Nm></Dbtr>
      <Cdtr><Nm>Bob</Nm></Cdtr>
      <Amt><InstdAmt Ccy="XYZ">100.00</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectMissingCurrencyAttribute) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Dbtr><Nm>Alice</Nm></Dbtr>
      <Cdtr><Nm>Bob</Nm></Cdtr>
      <Amt><InstdAmt>100.00</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

TEST_F(IsoParserTest, RejectMissingPaymentId) {
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <Dbtr><Nm>Alice</Nm></Dbtr>
      <Cdtr><Nm>Bob</Nm></Cdtr>
      <Amt><InstdAmt Ccy="EUR">100.00</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_FALSE(IsoParser::parse(xml, strlen(xml), payment));
}

// =============================================================================
// Edge Case Tests
// =============================================================================

TEST_F(IsoParserTest, HandleLongNames) {
    // Names longer than 63 chars should be truncated safely
    const char* xml = R"(<?xml version="1.0"?>
<Document>
  <CstmrCdtTrfinitn>
    <PmtInf>
      <PmtId><UETR>test-uetr</UETR></PmtId>
      <Dbtr><Nm>This Is A Very Long Name That Exceeds The Maximum Buffer Size Of Sixty Three Characters</Nm></Dbtr>
      <Cdtr><Nm>Bob</Nm></Cdtr>
      <Amt><InstdAmt Ccy="EUR">100.00</InstdAmt></Amt>
    </PmtInf>
  </CstmrCdtTrfinitn>
</Document>)";

    EXPECT_TRUE(IsoParser::parse(xml, strlen(xml), payment));

    // Should be truncated to 63 chars (null terminator at 64)
    EXPECT_EQ(strlen(payment.debtor_name), 63);
}

TEST_F(IsoParserTest, HandleEmptyDocument) {
    const char* xml = "";
    EXPECT_FALSE(IsoParser::parse(xml, 0, payment));
}

TEST_F(IsoParserTest, HandleMinimalValidPayment) {
    const char* xml = R"(<Document><CstmrCdtTrfinitn><PmtInf>
      <PmtId><UETR>x</UETR></PmtId>
      <Dbtr><Nm>A</Nm></Dbtr>
      <Cdtr><Nm>B</Nm></Cdtr>
      <Amt><InstdAmt Ccy="EUR">0.01</InstdAmt></Amt>
    </PmtInf></CstmrCdtTrfinitn></Document>)";

    EXPECT_TRUE(IsoParser::parse(xml, strlen(xml), payment));
    EXPECT_EQ(payment.amount, 10000); // 0.01 * 10^6
}

int main(int argc, char **argv) {
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}
