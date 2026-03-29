export type ParkedCar = {
  plate: string;
  entryTime: number; // Timestamp in ms
  isEvent: boolean;
  eventFee?: number;
};

export type ParkingConfig = {
  pricePerMinute: number;
  firstHalfHourFlatRate: number;
  maxFaresPerDay: number;
};

export const PARKING_CONFIG: ParkingConfig = {
  pricePerMinute: 33.3,
  firstHalfHourFlatRate: 1300,
  maxFaresPerDay: 8000
};

export function calculateFee(entryTime: number, exitTime: number, isEvent?: boolean, eventFee?: number): number {
  if (isEvent && eventFee) {
    return eventFee;
  }
  const diffMs = exitTime - entryTime;
  const diffMinutes = Math.floor(diffMs / 60000);
  
  if (diffMinutes < 30) {
    return PARKING_CONFIG.firstHalfHourFlatRate;
  }
  
  let total = diffMinutes * PARKING_CONFIG.pricePerMinute;
  
  // Ensure minimum is the first half hour flat rate if it goes over 30 mins but somehow is less (which based on 33.3 * 30 = 999 < 1300, yes, it could be).
  if (total < PARKING_CONFIG.firstHalfHourFlatRate) {
    total = PARKING_CONFIG.firstHalfHourFlatRate;
  }
  
  if (total > PARKING_CONFIG.maxFaresPerDay) {
    return PARKING_CONFIG.maxFaresPerDay;
  }
  
  return Math.round(total);
}
