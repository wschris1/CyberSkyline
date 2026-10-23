# Map Itinerary: how to solve

## Steps

1. Open each three-word address in the what3words map. Inspect the surrounding map labels to identify the nearby business, summit, and named trail. Cross-check the trail at both endpoints so a short local spur is not mistaken for the through trail.
2. Obtain the latitude and longitude of both points from the map or its share links. Keep the coordinates in decimal degrees and record which point is which.
3. Compute the shortest surface distance with the Haversine formula. Convert degrees to radians, use a consistent Earth radius (for example, 6,371 km), and ignore altitude as the question directs:

   ```python
   from math import asin, cos, radians, sin, sqrt

   def great_circle_km(lat1, lon1, lat2, lon2):
       lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
       dlat, dlon = lat2 - lat1, lon2 - lon1
       a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
       return 2 * 6371 * asin(sqrt(a))
   ```

4. Use an official source for the *entire* trail length, then apply the rounding requested in the question. The point-to-point great-circle result and the official trail length answer different questions.
