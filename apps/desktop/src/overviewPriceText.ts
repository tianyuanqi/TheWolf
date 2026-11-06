/** 指数点位仅在文字展示时四舍五入到两位；不得用于绘图、比较或金融计算。 */
export function priceText(value: string | null | undefined, group = false): string {
  if (value == null) return "暂无数据";
  if (!/^-?\d+(?:\.\d+)?$/.test(value)) throw new Error("指数显示值无效");
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = (negative ? value.slice(1) : value).split(".");
  const digits = fraction.padEnd(3, "0");
  const cents = BigInt(whole) * 100n + BigInt(digits.slice(0, 2)) + (digits[2] >= "5" ? 1n : 0n);
  const integer = (cents / 100n).toString();
  return (negative && cents !== 0n ? "-" : "")
    + (group ? integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",") : integer)
    + "." + (cents % 100n).toString().padStart(2, "0");
}
