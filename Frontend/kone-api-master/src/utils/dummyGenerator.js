// const generateDummyVideo = async() =>{
//     return{
//         // videoUrl: "http://dummy-storage.com/generate.mp4"
//        videoUrl: "https://www.pexels.com/video/dhaka-city-skyline-at-sunset-35233241"
//     };
// };

// module.exports = generateDummyVideo;

const generateDummyVideo = async () => {
  return {
    videoBuffer: Buffer.from('FAKE_VIDEO_DATA'),
  };
};

module.exports = generateDummyVideo;
