"use client";

import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import BulkUploadScreen from "@/components/BulkUploadScreen";

export default function SalesUploadPage() {
  return (
    <AuthGuard>
      <Shell>
        <BulkUploadScreen
          category="SALES"
          title="Upload Sales Invoices"
          description="Upload multiple sales invoices (PDF, JPG, PNG) in one batch. Each invoice is extracted and classified independently, then sent to the sales ledger once approved."
          acceptHint="PDF, JPG, PNG — multiple files supported"
        />
      </Shell>
    </AuthGuard>
  );
}
