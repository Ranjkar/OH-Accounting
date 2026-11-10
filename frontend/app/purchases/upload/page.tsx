"use client";

import { useTranslations } from "next-intl";
import AuthGuard from "@/components/AuthGuard";
import Shell from "@/components/Shell";
import BulkUploadScreen from "@/components/BulkUploadScreen";

export default function PurchasesUploadPage() {
  const t = useTranslations("purchasesUpload");
  return (
    <AuthGuard>
      <Shell>
        <BulkUploadScreen
          category="PURCHASES"
          title={t("title")}
          description={t("description")}
          acceptHint={t("acceptHint")}
        />
      </Shell>
    </AuthGuard>
  );
}
