"use client";

import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import BulkUploadScreen from "@/components/BulkUploadScreen";

export default function PurchasesUploadPage() {
  return (
    <AuthGuard>
      <Shell>
        <BulkUploadScreen
          category="PURCHASES"
          title="Upload Purchase Invoices"
          description="Upload multiple supplier invoices and expense receipts (PDF, JPG, PNG, XLSX, CSV) in one batch. Input VAT eligibility is assessed per line and flagged for review when uncertain."
          acceptHint="PDF, JPG, PNG, XLSX, CSV — multiple files supported"
        />
      </Shell>
    </AuthGuard>
  );
}
