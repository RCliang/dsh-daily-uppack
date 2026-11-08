// dsh-chouka 的系统定位助手：一次性取本机坐标（CoreLocation，WGS-84）
// 编译：xcrun swiftc -O -o locate-core locate.swift
// 运行：./locate-core            → 打印 {"lat":..,"lng":..,"accuracy":..} 或 {"error":".."}
//       CHOUKA_LOCATE_TEST=1 ./locate-core → 只验证能跑，不触发定位授权
// 首次运行 macOS 会弹「…想要访问你的位置」系统授权框（归属于调用方 App），允许一次即可。

import CoreLocation
import Foundation

if ProcessInfo.processInfo.environment["CHOUKA_LOCATE_TEST"] == "1" {
    print("{\"ok\":true,\"mode\":\"test\"}")
    exit(0)
}

final class Delegate: NSObject, CLLocationManagerDelegate {
    let done = DispatchSemaphore(value: 0)
    func locationManager(_ m: CLLocationManager, didUpdateLocations ls: [CLLocation]) {
        guard let l = ls.last else { return }
        print(String(format: "{\"lat\":%.8f,\"lng\":%.8f,\"accuracy\":%.0f}",
                     l.coordinate.latitude, l.coordinate.longitude, l.horizontalAccuracy))
        exit(0)
    }
    func locationManager(_ m: CLLocationManager, didFailWithError e: Error) {
        let code = (e as? CLError)?.code
        let hint: String
        switch code {
        case .denied:
            hint = "授权被拒绝：在系统授权框点「允许」，或去 系统设置 → 隐私与安全性 → 定位服务 放行本应用"
        case .locationUnknown:
            hint = "暂时拿不到位置，稍后再试"
        case .network:
            hint = "定位服务网络不可用"
        default:
            hint = e.localizedDescription
        }
        let msg = String(describing: hint).replacingOccurrences(of: "\"", with: "'")
        print("{\"error\":\"\(msg)\",\"code\":\(code?.rawValue ?? -1)}")
        exit(1)
    }
}

let delegate = Delegate()
let manager = CLLocationManager()
manager.delegate = delegate
manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
manager.startUpdatingLocation()

DispatchQueue.global().asyncAfter(deadline: .now() + 25) {
    print("{\"error\":\"timeout\"}")
    exit(2)
}
RunLoop.main.run()
