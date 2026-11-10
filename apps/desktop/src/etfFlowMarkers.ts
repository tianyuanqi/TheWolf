/** 只定位图形：交易日居中，非交易日按日历距离置于相邻交易日之间；不补数据点或改变标注日期。 */
export function placeEtfMarkers<T extends { id: string; date: string }>(dates: string[], markers: T[]) {
  if (!dates.length) return [];
  const stamp = (date: string) => Date.parse(date + 'T00:00:00Z');
  return markers.flatMap(marker => {
    if (marker.date < dates[0] || marker.date > dates[dates.length - 1]) return [];
    const right = dates.findIndex(date => date >= marker.date);
    const exact = dates[right] === marker.date;
    const index = exact ? right : right - 1
      + (stamp(marker.date) - stamp(dates[right - 1])) / (stamp(dates[right]) - stamp(dates[right - 1]));
    return [{ marker, position: (index + 0.5) / dates.length, nonTrading: !exact }];
  });
}
