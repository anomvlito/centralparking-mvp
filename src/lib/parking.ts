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
  
  if (diffMinutes <= 0) return 0;
  
  let total = diffMinutes * PARKING_CONFIG.pricePerMinute;
  
  if (total > PARKING_CONFIG.maxFaresPerDay) {
    return PARKING_CONFIG.maxFaresPerDay;
  }
  
  return Math.round(total);
}

