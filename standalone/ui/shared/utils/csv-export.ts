/**
 * Utility to convert extracted bank statement JSON data into a flat CSV.
 */

export interface Transaction {
  date?: string;
  description?: string;
  amount?: number | string;
  transaction_type?: string;
  category?: string;
  balance?: number | string;
  source_file?: string;
  [key: string]: any;
}

/**
 * Flattens multiple batch file results into a single CSV string.
 */
export function generateMergedCSV(files: any[]): string {
  const allTransactions: Transaction[] = [];

  for (const file of files) {
    const data = file.extracted_data || {};
    const transactions = data.transactions || [];
    const filename = file.filename || "unknown";

    for (const tx of transactions) {
      allTransactions.push({
        ...tx,
        source_file: filename,
        // Ensure some fields exist for the CSV header
        date: tx.date || "",
        description: tx.description || "",
        amount: tx.amount ?? 0,
        transaction_type: tx.transaction_type || "",
        category: tx.category || "",
        balance: tx.balance ?? "",
      });
    }
  }

  if (allTransactions.length === 0) {
    return "date,description,amount,transaction_type,category,balance,source_file\n";
  }

  // Sort by date if possible
  allTransactions.sort((a, b) => (a.date || "").localeCompare(b.date || ""));

  const headers = ["date", "description", "amount", "transaction_type", "category", "balance", "source_file"];
  
  const csvRows = [
    headers.join(","),
    ...allTransactions.map(tx => 
      headers.map(header => {
        const val = tx[header] ?? "";
        const escaped = String(val).replace(/"/g, '""');
        return `"${escaped}"`;
      }).join(",")
    )
  ];

  return csvRows.join("\n");
}

/**
 * Triggers a browser download of a string as a file.
 */
export function downloadBlob(content: string, filename: string, contentType: string) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
