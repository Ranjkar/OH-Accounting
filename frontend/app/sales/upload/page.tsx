"use client";

import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import BulkUploadScreen from "@/components/BulkUploadScreen";

export default function SalesUploadPage() {
  const t = useTranslations("invoices");
  return (
    <AuthGuard>
      <Shell>
        <BulkUploadScreen
          category="SALES"
          title={t("uploadSalesTitle")}
          description={t("uploadSalesDescription")}
          acceptHint={t("acceptHint")}
        />
      </Shell>
    </AuthGuard>
  );
}
